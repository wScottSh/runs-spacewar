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
HEADER_KEYS = {"entry", "inputs", "mirrors", "native"}
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
    sense = [v & 0o77 for v in lcg(4, len(ac_values))]
    return [simh.Inputs(a, i, b, w) for a, i, b, w in zip(ac_values, io, byname, sense)]


@dataclass
class Program:
    path: Path
    entries: list[ir.Signature]
    calls: list[simh.Inputs]
    words: list[ir.Word]
    placed: list[ir.Datum]
    functions: list[ir.Function]
    spaces: list[ir.Space]
    unit: ir.Unit
    mirrors: str | None = None      # the lifted routine this program copies the shape of
    native: dict[str, str] = None   # entry -> the function the native build calls instead


PREFIX = "zz"


def lower(path: Path, prefix: str = PREFIX) -> tuple[ir.Unit, list[ir.Word]]:
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
    native = dict(pair.split(":", 1) for pair in fields["native"].split(",")) if "native" in fields else {}
    if "inputs" in fields:
        lo, hi = (int(x, 8) for x in fields["inputs"].split(".."))
        ac = list(range(lo, hi + 1))
    else:
        ac = default_ac()
    unit, words = lower(path)
    entries = [unit.signatures[name] for name in fields["entry"].split(",")]
    placed = list(unit.data.values())
    functions = [t for t in unit.items if isinstance(t, ir.Function)]
    spaces = [t for t in unit.items if isinstance(t, ir.Space)]
    for entry, stand_in in native.items():
        if entry not in unit.signatures or stand_in not in unit.signatures or \
                unit.signatures[entry].params != unit.signatures[stand_in].params:
            raise SystemExit(f"{path}: native={entry}:{stand_in} names two functions with the same parameters")
    return Program(path, entries, calls_for(ac), words, placed, functions, spaces, unit,
                   fields.get("mirrors"), native)


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


DISPLAY_WORD = re.compile(r"^\s*\d*\s+([0-7]{5}) ([0-7]{6})\s+(?:\w+,)?\s*dpy\b", re.M)


def display_words(lst: Path) -> dict[int, int]:
    """Address -> word of every display instruction in an assembled listing."""
    return {int(a, 8): int(w, 8) for a, w in DISPLAY_WORD.findall(lst.read_text(errors="replace"))}


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
        if m.plotted != n.plotted:
            k = next((k for k, (a, b) in enumerate(zip(m.plotted, n.plotted)) if a != b),
                     min(len(m.plotted), len(n.plotted)))
            show = lambda ps: " ".join(f"{w:06o}@{x:06o},{y:06o}" for w, x, y in ps[k:k + 2]) or "-"
            bad.append(f"plotted {len(m.plotted)} points in simh, {len(n.plotted)} native; from point {k} "
                       f"simh {show(m.plotted)} native {show(n.plotted)}")
        if bad:
            diffs.append(f"ac {c.ac:06o} io {c.io:06o} byname {c.byname:06o} sense {c.sense:02o}: "
                         + ", ".join(bad))
    if len(native) != len(calls):
        diffs.append(f"native build produced {len(native)} results for {len(calls)} calls")
    return diffs


def watched(prog: Program) -> list[tuple[str, str, int, str]]:
    """(label, Macro symbol, offset, native expression) of every word compared
    after each call: placed words, reserved words (not pointers, whose native
    value is a host address), and the entry words of defined JDA functions."""
    out = []
    for d in prog.placed:
        out += [(f"{d.name}[{k}]", d.sym, k, f"{d.name}[{k}]") if d.array else (d.name, d.sym, 0, d.name)
                for k in range(len(d.values))]
    out += [(name, s.sym, 0, name) for name, s in prog.unit.objects.items() if isinstance(s, ir.Pool)]
    for s in prog.spaces:
        if not s.pointer:
            out += [(f"{s.name}[{k}]", s.sym, k, f"{s.name}[{k}]") if s.array else
                    (s.name, s.sym, 0, s.name) for k in range(s.size)]
    out += [(f"entry word of {f.sig.name}", f.sig.sym, 0, reference.cell(f.sig.name))
            for f in prog.functions if reference.entry_param(f.sig)]
    return out


def stand_in_watch(watch: list[tuple[str, str, int, str]], entry: str,
                   stand_in: str | None) -> list[tuple[str, str, int, str]]:
    """With a native stand-in, the stand-in plays the entry: natively the
    entry's entry word is the stand-in's, and the stand-in's own entry word,
    which the machine never fills, is not compared."""
    if stand_in is None:
        return watch
    mine, theirs = reference.cell(entry), reference.cell(stand_in)
    return [(label, sym, k, theirs if expr == mine else expr)
            for label, sym, k, expr in watch if expr != theirs]


def run_program(prog: Program, simh_bin: Path, macro1: Path, work: Path) -> list[str]:
    rim, symbols = assemble(prog, macro1, work)
    placed = reference.placements(prog.unit, symbols)
    diffs = []
    for sig in prog.entries:
        watch = stand_in_watch(watched(prog), sig.name, prog.native.get(sig.name))
        machine = simh.run_jda(simh_bin, rim, symbols[sig.sym], prog.calls, sig.byname,
                               [symbols[sym] + k for _, sym, k, _ in watch],
                               inline=sig.inline_count > sig.byname,
                               display=display_words(rim.with_suffix(".lst")))
        binary = reference.build([prog.path], sig, work / f"{prog.path.stem}-{sig.name}",
                                 [expr for *_, expr in watch], placed,
                                 native=prog.native.get(sig.name))
        native = reference.run(binary, prog.calls)
        diffs += [f"{sig.name} {d}" for d in
                  compare(prog.calls, machine, native, sig, [label for label, *_ in watch])]
    return diffs


def rules_used(words: list[ir.Word]) -> Counter:
    return Counter(r for w in words if not isinstance(w, ir.Break) for r in (w.rule, *w.via))


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
