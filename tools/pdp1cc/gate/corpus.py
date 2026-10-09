"""G2: compile each non-Spacewar corpus program with pdp1cc, assemble it with
macro1, run each entry in SIMH, and compare every call's AC, IO (for dword
results), return point and every placed word with the native reference
build. Every entry word of a JDA function is compared too. Then check rule coverage: every registered rule must be exercised by
at least two corpus programs that do not mirror a lifted routine, as the
rule of a word or as a rule that chose part of that word (`via`)."""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .. import dialect, emit, front, ir, layout
from ..rules import RULES
from . import reference, simh

HEADER = re.compile(r"/\* corpus: ((?:\w+=\S+ ?)+)\*/")
HEADER_KEYS = {"entry", "inputs", "mirrors"}
ORIGIN = 0o100
MIN_PROGRAMS_PER_RULE = 2


def lcg(seed: int, n: int) -> list[int]:
    x, out = seed, []
    for _ in range(n):
        x = (x * 1103515245 + 12345) % (1 << 31)
        out.append(x >> 13 & ir.WORD_MASK)
    return out


def default_ac() -> list[int]:
    edges = [0, 1, 2, 3, 7, 0o10, 0o777, 0o7777, 0o177777, (1 << 17) - 1]
    edges += [ir.WORD_MASK ^ v for v in edges]
    return edges + lcg(1, 300)


def calls_for(ac_values: list[int]) -> list[simh.Inputs]:
    io = lcg(2, len(ac_values))
    byname = lcg(3, len(ac_values))
    return [simh.Inputs(a, i, b) for a, i, b in zip(ac_values, io, byname)]


@dataclass
class Program:
    path: Path
    entries: list[ir.Signature]
    calls: list[simh.Inputs]
    words: list[ir.Word]
    placed: list[ir.Datum]
    functions: list[ir.Function]
    mirrors: str | None = None      # the lifted routine this program copies the shape of


def lower(path: Path, prefix: str = "zz") -> tuple[ir.Unit, list[ir.Word]]:
    unit = dialect.lower_unit(front.parse(path), prefix)
    return unit, layout.place(unit, prefix)


def load(path: Path) -> Program:
    m = HEADER.search(path.read_text())
    if not m:
        raise SystemExit(f"{path}: missing `/* corpus: entry=NAME[,NAME] [inputs=A..B] "
                         "[mirrors=ROUTINE] */`")
    fields = dict(kv.split("=", 1) for kv in m.group(1).split())
    if fields.keys() - HEADER_KEYS or "entry" not in fields:
        raise SystemExit(f"{path}: corpus header keys are {sorted(HEADER_KEYS)}, entry required")
    if "inputs" in fields:
        lo, hi = (int(x, 8) for x in fields["inputs"].split(".."))
        ac = list(range(lo, hi + 1))
    else:
        ac = default_ac()
    unit, words = lower(path)
    entries = [unit.signatures[name] for name in fields["entry"].split(",")]
    placed = [t for t in unit.items if isinstance(t, ir.Datum)]
    functions = [t for t in unit.items if isinstance(t, ir.Function)]
    return Program(path, entries, calls_for(ac), words, placed, functions, fields.get("mirrors"))


def assemble(prog: Program, macro1: Path, work: Path) -> tuple[Path, dict[str, int]]:
    work.mkdir(parents=True, exist_ok=True)
    mac = work / f"{prog.path.stem}.mac"
    mac.write_text(f"corpus {prog.path.stem}\n{ORIGIN:o}/\n" + emit.emit(prog.words)
                   + f"\tconstants\n\tvariables\n\tstart {ORIGIN:o}\n")
    for ext in (".rim", ".lst"):
        mac.with_suffix(ext).unlink(missing_ok=True)
    subprocess.run([str(macro1), "-r", "-d", mac.name], cwd=work, check=True, capture_output=True)
    lst = mac.with_suffix(".lst").read_text()
    if "No errors detected" not in lst:
        raise SystemExit(f"{mac}: macro1 reported errors")
    symbols = {s: int(v, 8) for s, v in re.findall(r"^ (\w+)\s+([0-7]{6})$", lst, re.M)}
    return mac.with_suffix(".rim"), symbols


def compare(calls: list[simh.Inputs], machine: list[simh.Outcome], native: list[simh.Outcome],
            sig: ir.Signature, watch_names: list[str]) -> list[str]:
    """Differences between SIMH and the native build, one line per differing call."""
    diffs = []
    for c, m, n in zip(calls, machine, native):
        fields = [("AC", m.ac, n.ac), ("returned past", m.returned_past, n.returned_past)]
        if sig.returns == "dword":
            fields.append(("IO", m.io, n.io))
        fields += list(zip(watch_names, m.watched, n.watched))
        bad = [f"{k} simh {a:06o} native {b:06o}" for k, a, b in
               ((f[0], f[1], f[2]) for f in fields) if a != b]
        if bad:
            diffs.append(f"ac {c.ac:06o} io {c.io:06o} byname {c.byname:06o}: " + ", ".join(bad))
    if len(native) != len(calls):
        diffs.append(f"native build produced {len(native)} results for {len(calls)} calls")
    return diffs


def watched(prog: Program) -> list[tuple[str, str, str]]:
    """(label, Macro symbol, native expression) of every word compared after
    each call: the placed words and the entry words of defined JDA functions."""
    out = [(d.name, d.sym, d.name) for d in prog.placed]
    out += [(f"entry word of {f.sig.name}", f.sig.sym, reference.cell(f.sig.name))
            for f in prog.functions if reference.entry_param(f.sig)]
    return out


def run_program(prog: Program, simh_bin: Path, macro1: Path, work: Path) -> list[str]:
    rim, symbols = assemble(prog, macro1, work)
    watch = watched(prog)
    diffs = []
    for sig in prog.entries:
        machine = simh.run_jda(simh_bin, rim, symbols[sig.sym], prog.calls, bool(sig.inline_count),
                               [symbols[sym] for _, sym, _ in watch])
        binary = reference.build([prog.path], sig, work / f"{prog.path.stem}-{sig.name}",
                                 [expr for _, _, expr in watch])
        native = reference.run(binary, prog.calls)
        diffs += [f"{sig.name} {d}" for d in
                  compare(prog.calls, machine, native, sig, [label for label, _, _ in watch])]
    return diffs


def rules_used(words: list[ir.Word]) -> Counter:
    return Counter(r for w in words for r in (w.rule, *w.via))


def coverage(programs: list[Program], lift_words: dict[str, Counter]) -> tuple[list[str], bool]:
    """A rule needs MIN_PROGRAMS_PER_RULE users that do not mirror a lifted
    routine. Mirrors are listed in parentheses and do not count."""
    used = {p.path.stem: rules_used(p.words) for p in programs}
    mirror = {p.path.stem for p in programs if p.mirrors}
    lines = [f"{'rule':<18}{'lift words':>11}  independent corpus programs (mirrors)"]
    ok = True
    for r in RULES:
        users = [name for name, c in used.items() if c[r]]
        independent = [u for u in users if u not in mirror]
        mirrors = [u for u in users if u in mirror]
        lift = sum(c[r] for c in lift_words.values())
        flag = ""
        if len(independent) < MIN_PROGRAMS_PER_RULE:
            ok, flag = False, "  UNDER-TESTED"
        shown = ",".join(independent) + (f" ({','.join(mirrors)})" if mirrors else "")
        lines.append(f"{r:<18}{lift:>11}  {len(independent)} {shown}{flag}")
    return lines, ok


def gate(corpus_dir: Path, lift_files: list[Path], simh_bin: Path, macro1: Path, work: Path) -> int:
    programs = [load(p) for p in sorted(corpus_dir.glob("*.c"))]
    failed = False
    for prog in programs:
        try:
            diffs = run_program(prog, simh_bin, macro1, work)
        except subprocess.CalledProcessError as e:
            diffs = [f"{' '.join(map(str, e.cmd[:1]))} failed (exit {e.returncode})"]
        status = "ok" if not diffs else f"{len(diffs)} DIFFER"
        calls = len(prog.calls) * len(prog.entries)
        print(f"  {prog.path.name:<16} {calls:>5} calls  {len(prog.words):>3} words  {status}")
        for d in diffs[:5]:
            print("    " + d)
        failed |= bool(diffs)
    lift_words = {f.name: rules_used(lower(f)[1]) for f in lift_files}
    lines, ok = coverage(programs, lift_words)
    print("\n".join("  " + line for line in lines))
    return 1 if failed or not ok else 0
