"""Where play reaches the machine, as the oracle shows it.

SIMH runs the oracle image through the lift's scripted matches (the
scenarios of check-main-loop-frames.py: real play from the start address,
a control policy on the test word, every sense switch setting, the full
object table). CPU history records each instruction with its effective
address. Each data access is named by the place it lands in: a field of a
bound Record (pdp1.FIELDS), or the oracle listing's label or variable.

Play reaches the machine where the game's behavior depends on how the
PDP-1 lays out and runs the program, not on the rules the RUNS text states.
The tool reports each site of these kinds:

- one instruction reads or writes more than one place. A rule that names
  its Records touches the same places every time, so an instruction that
  lands in different ones is reading the layout (an index past an array,
  a pointer into the wrong table), or it is shared code handed a place.
- a read of core the tape never loaded, before the program wrote it: the
  power-on contents of core.
- a word written whole at run time and then executed: code the program
  generates.
- an instruction word read whole as a value, other than a cursor: code
  read as data.
- an indirect jump or xct to an address no label names, other than a
  return to just after a call.
- a halt.

Three idioms are counted, not listed: an instruction whose address field
the program steps or sets (dap, idx, isp on a code word: the cursors), an
instruction word used as the pointer of an indirect access, and a jump
back to just after the call that entered a subroutine.

The tool checks itself two ways. It follows core as the program writes it
and compares its copy with SIMH's at the end of every scenario. It models
the result of each add, subtract, shift and rotate and compares it with
the AC that SIMH shows after the instruction.

The report is a list of candidates. Which of them the game's behavior
depends on, the RUNS port and its checks decide.

Usage: uv run python tools/reach_oracle.py [--stops N]"""
from __future__ import annotations

import argparse
import importlib.util
import os
import multiprocessing
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

import pdp1
import runs

spec = importlib.util.spec_from_file_location("frames", pdp1.ROOT / "tools/check-main-loop-frames.py")
frames = importlib.util.module_from_spec(spec)
sys.modules["frames"] = frames
spec.loader.exec_module(frames)

HISTORY = 65536                 # SIMH's largest CPU history
READ = {"LAC", "LIO", "ADD", "SUB", "AND", "IOR", "XOR", "SAD", "SAS", "MUL", "DIV"}
WRITE_WHOLE = {"DAC", "DIO", "DZM"}
WRITE_PART = {"DAP", "DIP"}
STEP = {"IDX", "ISP"}
JUMP = {"JMP", "JSP"}
MEMORY = READ | WRITE_WHOLE | WRITE_PART | STEP | JUMP | {"JDA", "CAL", "XCT"}
OPCODES = {"LAC": 0o20, "LIO": 0o22, "ADD": 0o40, "SUB": 0o42, "AND": 0o02, "IOR": 0o04, "XOR": 0o06,
           "SAD": 0o50, "SAS": 0o52, "MUL": 0o54, "DIV": 0o56, "DAC": 0o24, "DIO": 0o32, "DZM": 0o34,
           "DAP": 0o26, "DIP": 0o30, "IDX": 0o44, "ISP": 0o46, "JMP": 0o60, "JSP": 0o62, "JDA": 0o17,
           "CAL": 0o16, "XCT": 0o10}
MNEMONIC = {v: k for k, v in OPCODES.items()}
ADDRESS = 0o7777
VARIABLE = re.compile(r"\\([a-z0-9]+)")


@dataclass(frozen=True)
class Step:
    pc: int
    ac: int                     # AC and IO before the instruction runs
    io: int
    ea: int | None              # for an xct, the address the executed word reached
    op: str
    indirect: bool
    address: int | None
    number: str | None          # the last number in the instruction text: an address, or a shift count


def parse_history(text: str) -> list[Step]:
    steps = []
    for line in text.splitlines():
        if len(line) < 38 or not line[:6].isdigit():
            continue
        tokens = line[37:].split("[")[0].split()
        if not tokens:
            continue
        op, indirect = tokens[0], len(tokens) > 1 and tokens[1] == "I"
        address = int(tokens[-1], 8) if op in MEMORY and re.fullmatch(r"[0-7]+", tokens[-1]) else None
        ea = int(line[29:35], 8) if line[29:35].strip() else None
        number = tokens[-1] if len(tokens) > 1 and tokens[-1].isdigit() else None
        steps.append(Step(int(line[:6], 8), int(line[11:17], 8), int(line[18:24], 8), ea, op, indirect,
                          address, number))
    return steps


class Places:
    """The name of every core address: a bound Record field, else the
    listing's variable at that address, else the nearest label at or below."""

    def __init__(self, oracle):
        sym = oracle.symbols
        text = (pdp1.ROOT / "build/oracle.lst").read_text(errors="replace")
        variables = {sym[v]: v for v in set(VARIABLE.findall(text)) if v in sym}
        labels = {a: frames.LABEL.match(w.text).group(1).split(",")[0].strip()
                  for a, w in oracle.words.items() if not w.literal and frames.LABEL.match(w.text)}
        self.labels = set(labels)
        prog = runs.program(runs.source())
        self.name: dict[int, str] = {}
        self.field: dict[int, str] = {}
        last = None
        free = sym["nnn"]           # past the object table: where the outline compiler writes its code
        for a in range(0o10000):
            if a in labels:
                last = (a, labels[a])
            if a >= free and a not in oracle.words:
                self.name[a] = f"nnn+{a - free:o}"
                self.field[a] = "free core"
            elif a in variables:
                self.name[a] = variables[a]
            elif last:
                self.name[a] = last[1] if last[0] == a else f"{last[1]}+{a - last[0]:o}"
            else:
                self.name[a] = f"{a:05o}"
        for (rec, fld), s in pdp1.FIELDS.items():
            count = prog.records[rec].count or 1
            for k in range(count):
                self.field[sym[s] + k] = f"{rec}.{fld}"
                self.name[sym[s] + k] = f"{rec}.{fld}" + (f"[{k:o}]" if prog.records[rec].count else "")

    def base(self, a: int) -> str:
        """The place without its index: a Record field, or the name itself."""
        return self.field.get(a, self.name[a])


@dataclass
class Seen:
    executed: set[int] = field(default_factory=set)
    whole_writes: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    part_writes: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    value_reads: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    pointer_reads: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    places: dict[int, Counter] = field(default_factory=lambda: defaultdict(Counter))
    power_on: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    far_jumps: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    arithmetic: dict[int, Counter] = field(default_factory=lambda: defaultdict(Counter))
    modelled: Counter = field(default_factory=Counter)     # results the tool predicted, by op
    mismodelled: Counter = field(default_factory=Counter)  # and got wrong
    halts: Counter = field(default_factory=Counter)
    stops: int = 0
    instructions: int = 0
    truncated: int = 0
    core_differs: list[int] = field(default_factory=list)   # where the tool's copy of core went wrong
    scenarios: list[str] = field(default_factory=list)

    def merge(self, other: "Seen") -> None:
        self.executed |= other.executed
        for name in ("whole_writes", "part_writes", "value_reads", "pointer_reads", "power_on", "far_jumps"):
            mine = getattr(self, name)
            for k, v in getattr(other, name).items():
                mine[k] |= v
        for k, v in other.places.items():
            self.places[k] += v
        for k, v in other.arithmetic.items():
            self.arithmetic[k] += v
        self.modelled += other.modelled
        self.mismodelled += other.mismodelled
        self.halts += other.halts
        self.stops += other.stops
        self.instructions += other.instructions
        self.truncated += other.truncated
        self.core_differs += other.core_differs
        self.scenarios += other.scenarios


def record(steps: list[Step], seen: Seen, places: Places, loaded: set[int], written: set[int],
           core: dict[int, int]) -> None:
    """Follows core as the program changes it, so that the word an xct runs
    is the word in core at that moment. SIMH lists an xct once, with the
    effective address of the word it ran."""
    for i, s in enumerate(steps):
        seen.executed.add(s.pc)
        op, site, ea, indirect, address = s.op, s.pc, s.ea, s.indirect, s.address
        while op == "XCT":
            target = core.get(address, 0) & ADDRESS if indirect else address
            if indirect:
                seen.pointer_reads[address].add(site)
                if target not in places.labels:
                    seen.far_jumps[site].add(target)
            seen.executed.add(target)
            word = core.get(target, 0)
            op, site = MNEMONIC.get(word >> 12 & 0o76, "?"), target
            indirect, address = bool(word & 0o10000), word & ADDRESS
        if i + 1 < len(steps):
            operand = core.get(ea, 0) if ea is not None and op in READ else None
            arithmetic(op, s, operand, steps[i + 1].ac, site, seen)
        if op not in MEMORY:
            continue
        if indirect:
            seen.pointer_reads[address].add(site)
        if op in ("JDA", "CAL"):
            ea = 0o100 if op == "CAL" else (ea if indirect else address)
            seen.whole_writes[ea].add(site)
            written.add(ea)
            core[ea] = s.ac
            seen.places[site][places.base(ea)] += 1
            continue
        if ea is None:
            continue
        if op in JUMP:
            if indirect and ea not in places.labels:
                seen.far_jumps[site].add(ea)
            continue
        seen.places[site][places.base(ea)] += 1
        if op in READ or op in STEP:
            if ea not in loaded and ea not in written:
                seen.power_on[ea].add(site)
            seen.value_reads[ea].add(site)
        if op in WRITE_WHOLE:
            seen.whole_writes[ea].add(site)
            core[ea] = {"DAC": s.ac, "DIO": s.io, "DZM": 0}[op]
        elif op == "DAP":
            seen.part_writes[ea].add(site)
            core[ea] = core.get(ea, 0) & ~ADDRESS | s.ac & ADDRESS
        elif op == "DIP":
            seen.part_writes[ea].add(site)
            core[ea] = core.get(ea, 0) & ADDRESS | s.ac & ~ADDRESS & 0o777777
        elif op in STEP:
            seen.part_writes[ea].add(site)
            core[ea] = steps[i + 1].ac if i + 1 < len(steps) else core.get(ea, 0)
        if op in WRITE_WHOLE or op in WRITE_PART or op in STEP:
            written.add(ea)


def signed(v: int) -> int:
    return -(v ^ runs.MASK) if v & runs.SIGN else v


ROTATE = {"RAL", "RAR", "RIL", "RIR", "RCL", "RCR"}
TESTS = {"SZA", "SMA", "SPA", "SAD", "SAS"}


def arithmetic(op: str, s: Step, operand: int | None, after: int, site: int, seen: Seen) -> None:
    """The word's machine behavior at one instruction: where the PDP-1's
    result is not the integer result, or depends on how a negative number
    is encoded in bits. Also checks the tool's model of the instruction
    against the AC SIMH shows after it."""
    kinds = seen.arithmetic[site]
    a = runs.W(s.ac)
    if op in ("ADD", "SUB"):
        b = runs.W(operand)
        model = (runs.add if op == "ADD" else runs.sub)(a, b).v
        exact = signed(s.ac) + (signed(operand) if op == "ADD" else -signed(operand))
        if abs(exact) > 0o377777:
            kinds["wraps around"] += 1
        if after == runs.MASK:
            kinds["makes minus zero"] += 1
    elif op in ("SAR", "SAL") and s.number:
        n = int(s.number)
        model = (runs.sar if op == "SAR" else runs.sal)(a, n).v
        v = signed(s.ac)
        if op == "SAR" and v < 0 and v % (1 << n):
            kinds["shift right rounds toward zero"] += 1
        if op == "SAL" and signed(model) != v * (1 << n):
            kinds["shift left loses bits"] += 1
    elif op in ("RAL", "RAR") and s.number:
        model = (runs.ral if op == "RAL" else runs.rar)(a, int(s.number)).v
        kinds["rotates bits"] += 1
    elif op in ROTATE or op in ("SCL", "SCR"):
        if op in ROTATE or s.ac & runs.SIGN:
            kinds["rotates bits" if op in ROTATE else "combined shift of a negative"] += 1
        return
    elif op in ("AND", "IOR", "XOR"):
        if (s.ac | operand) & runs.SIGN:
            kinds["bit operation on a negative"] += 1
        return
    elif op in TESTS:
        if s.ac == runs.MASK or (operand == runs.MASK and op in ("SAD", "SAS")):
            kinds["tests minus zero"] += 1
        return
    elif op in ("MUL", "DIV"):
        kinds["multiply or divide step"] += 1
        return
    else:
        return
    seen.modelled[op] += 1
    if model != after:
        seen.mismodelled[op] += 1


def run(scenario, oracle, places: Places, stops: int) -> Seen:
    seen = Seen(scenarios=[scenario.name])
    sym = oracle.symbols
    seam = sym["ml0"]
    core = {a: w.value for a, w in oracle.words.items()}
    for name, value in scenario.deposits:
        core[sym[name]] = value
    loaded = set(core)
    written: set[int] = set()
    setup = [f"dep SS {scenario.sense:o}", f"dep {sym['ran']:o} {scenario.seed:o}",
             *(f"dep {sym[name]:o} {value:o}" for name, value in scenario.deposits),
             f"break {seam:o}", f"set cpu history={HISTORY}"]
    m = frames.Machine(oracle.rim, setup)
    controls = frames.Controls(scenario.policy, scenario.seed)
    repeats, last_halt = 0, None
    try:
        m.send(f"dep TW {controls.next(frames.Stop('frame', seam)):o}")
        m.read()
        m.send(f"go {scenario.start:o}")
        while seen.stops < stops:
            stop = frames.parse_run(m.read(), seam)
            seen.stops += 1
            m.send(f"show cpu history={HISTORY}")
            steps = parse_history(m.read())
            seen.instructions += len(steps)
            seen.truncated += len(steps) >= HISTORY
            m.send("set cpu history=0")
            m.read()
            m.send(f"set cpu history={HISTORY}")
            m.read()
            record(steps, seen, places, loaded, written, core)
            if stop.kind == "halt":
                seen.halts[stop.pc] += 1
                repeats = repeats + 1 if stop.pc == last_halt else 0
                last_halt = stop.pc
                if repeats >= frames.REPEATED_HALTS:
                    break
            else:
                last_halt = None
            m.send(f"dep TW {controls.next(stop):o}")
            m.read()
            m.send("cont")
        m.send("ex 0-7777")
        actual = {int(a, 8): int(v, 8) for a, v in re.findall(r"^([0-7]+):\s+([0-7]+)", m.read(), re.M)}
        seen.core_differs = sorted(a for a, v in actual.items() if core.get(a, 0) != v)
    finally:
        m.close()
    return seen


def where(oracle, places: Places, a: int) -> str:
    w = oracle.words.get(a)
    src = f"line {w.line}: {w.text.split('/')[0].strip()}" if w else "not on the tape"
    return f"{a:05o} {places.name[a]:<14} {src}"


def spans(addresses: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a in addresses:
        if out and a == out[-1][1] + 1:
            out[-1] = (out[-1][0], a)
        else:
            out.append((a, a))
    return out


def report(oracle, places: Places, seen: Seen) -> None:
    run_writes = {a for a in seen.whole_writes if a in seen.executed}
    stepped = {a for a in seen.part_writes if a in seen.executed} - run_writes
    print(f"scenarios: {len(seen.scenarios)}; stops: {seen.stops}; instructions: {seen.instructions}; "
          f"stops whose history overflowed: {seen.truncated}; "
          f"words where the tool's copy of core differs from SIMH's at the end: {len(seen.core_differs)}")
    if seen.core_differs:
        print("  " + ", ".join(f"{a:05o} {places.name[a]}" for a in seen.core_differs[:20]))

    shared = {pc: c for pc, c in seen.places.items() if len(c) > 1}
    print(f"\none instruction, several places: {len(shared)} sites")
    for pc in sorted(shared):
        c = shared[pc]
        print(f"  {where(oracle, places, pc)}")
        print(f"      {', '.join(f'{p} x{n}' for p, n in c.most_common(8))}"
              + (f" (+{len(c) - 8} more)" if len(c) > 8 else ""))

    print(f"\nreads of core the tape never loaded, before any write: {len(seen.power_on)} words")
    for a in sorted(seen.power_on):
        print(f"  {places.name[a]:<14} {a:05o} read at " + ", ".join(f"{pc:05o}" for pc in sorted(seen.power_on[a])))

    print(f"\nwords written whole, then executed (generated code): {len(run_writes)} words")
    for first, last in spans(sorted(run_writes)):
        writers = sorted({places.name[pc].split("+")[0] for a in range(first, last + 1)
                          for pc in seen.whole_writes.get(a, ())})
        span = f"{first:05o}-{last:05o}" if last > first else f"{first:05o}"
        print(f"  {span:<12} {places.name[first]:<10} {last - first + 1:>4} words, written by {', '.join(writers)}")

    code_values = {a: s for a, s in seen.value_reads.items() if a in seen.executed and a not in stepped}
    print(f"\ninstruction words read whole as values, other than cursors: {len(code_values)} words")
    for first, last in spans(sorted(code_values)):
        readers = sorted({f"{pc:05o} {places.name[pc]}" for a in range(first, last + 1) for pc in code_values[a]})
        span = f"{first:05o}-{last:05o}" if last > first else f"{first:05o}"
        print(f"  {span:<12} {places.name[first]:<10} {last - first + 1:>4} words, read at {', '.join(readers[:4])}")

    def returns(t: int) -> bool:
        """A jump back to just after a call: a subroutine's return."""
        return any((w := oracle.words.get(t - k)) and w.value >> 12 & 0o76 in (0o16, 0o62) for k in (1, 2, 3))

    far = {pc: {t for t in ts if not returns(t)} for pc, ts in seen.far_jumps.items()}
    far = {pc: ts for pc, ts in far.items() if ts}
    print(f"\nindirect jumps and xcts to an address no label names, other than returns from a call: {len(far)} sites")
    for pc in sorted(far):
        targets = sorted(far[pc])
        print(f"  {where(oracle, places, pc)}")
        print(f"      to {len(targets)} addresses: " + ", ".join(f"{t:05o} {places.name[t]}" for t in targets[:6]))

    print(f"\nthe word's machine behavior: {sum(1 for c in seen.arithmetic.values() if c)} sites")
    print("  the tool's model of each instruction against SIMH's AC after it: "
          + ", ".join(f"{op} {seen.modelled[op] - seen.mismodelled[op]}/{seen.modelled[op]}"
                      for op in sorted(seen.modelled)))
    totals = Counter()
    for c in seen.arithmetic.values():
        totals.update({k: 1 for k in c})
    for kind, n in totals.most_common():
        sites = sorted((pc for pc, c in seen.arithmetic.items() if c[kind]), key=lambda pc: -seen.arithmetic[pc][kind])
        print(f"  {kind}: {n} sites")
        for pc in sites:
            print(f"      {where(oracle, places, pc)}  x{seen.arithmetic[pc][kind]}")

    print(f"\nhalts: " + (", ".join(f"{where(oracle, places, pc)} x{n}" for pc, n in seen.halts.items()) or "none"))

    pointers = {a for a in seen.pointer_reads if a in seen.executed}
    print(f"\nidioms, counted: {len(stepped)} instructions whose address field the program steps (cursors); "
          f"{len(pointers)} instruction words used as pointers; "
          f"{sum(len(ts) for ts in seen.far_jumps.values()) - sum(len(ts) for ts in far.values())} return addresses")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stops", type=int, default=600, help="frames and halts per scenario")
    parser.add_argument("--jobs", type=int, default=min(len(frames.SCENARIOS), os.cpu_count() or 1))
    args = parser.parse_args()
    cfg, _ = frames.program.load(frames.ROOT / "lift.toml")
    oracle = frames.image(frames.ORACLE_RIM, frames.ROOT / cfg["oracle_listing"])
    places = Places(oracle)
    n = len(frames.SCENARIOS)
    with ProcessPoolExecutor(args.jobs, mp_context=multiprocessing.get_context("fork")) as pool:
        results = list(pool.map(run, frames.SCENARIOS, [oracle] * n, [places] * n, [args.stops] * n))
    seen = Seen()
    for r in results:
        seen.merge(r)
    report(oracle, places, seen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
