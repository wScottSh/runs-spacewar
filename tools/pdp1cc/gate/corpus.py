"""G2: compile each non-Spacewar corpus program with pdp1cc, assemble it with
macro1, run it in SIMH, and compare every call's AC and every placed word
with the native reference build. Then check rule coverage: every registered
rule must be exercised by at least two corpus programs."""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .. import dialect, emit, front, ir, layout
from ..rules import RULES
from . import reference, simh

HEADER = re.compile(r"/\* corpus: entry=(\w+)(?: inputs=([0-7]+)\.\.([0-7]+))? \*/")
ORIGIN = 0o100
MIN_PROGRAMS_PER_RULE = 2


def default_inputs() -> list[int]:
    edges = [0, 1, 2, 3, 7, 0o10, 0o777, 0o7777, 0o177777, (1 << 17) - 1]
    edges += [ir.WORD_MASK ^ v for v in edges]
    x, rand = 1, []
    for _ in range(300):
        x = (x * 1103515245 + 12345) % (1 << 31)
        rand.append(x >> 13 & ir.WORD_MASK)
    return edges + rand


@dataclass
class Program:
    path: Path
    entry: str
    inputs: list[int]
    words: list[ir.Word]
    placed: list[str]


def load(path: Path) -> Program:
    m = HEADER.search(path.read_text())
    if not m:
        raise SystemExit(f"{path}: missing `/* corpus: entry=NAME [inputs=A..B] */`")
    inputs = (list(range(int(m.group(2), 8), int(m.group(3), 8) + 1))
              if m.group(2) else default_inputs())
    unit = dialect.lower_unit(front.parse(path))
    placed = [t.sym for t in unit.items if isinstance(t, ir.Datum)]
    return Program(path, m.group(1), inputs, layout.place(unit, "zz"), placed)


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


def run_program(prog: Program, simh_bin: Path, macro1: Path, work: Path) -> list[str]:
    rim, symbols = assemble(prog, macro1, work)
    machine = simh.run_jda(simh_bin, rim, symbols[prog.entry], prog.inputs,
                           [symbols[p] for p in prog.placed])
    native = reference.run(
        reference.build(prog.path, prog.entry, work / prog.path.stem, prog.placed), prog.inputs)
    names = ["AC"] + prog.placed
    diffs = []
    for x, m, n in zip(prog.inputs, machine, native):
        if m != n:
            diffs.append(f"input {x:06o}: " + ", ".join(
                f"{k} simh {a:06o} native {b:06o}" for k, a, b in zip(names, m, n) if a != b))
    if len(native) != len(prog.inputs):
        diffs.append(f"native build produced {len(native)} results for {len(prog.inputs)} inputs")
    return diffs


def coverage(programs: list[Program], lift_words: dict[str, Counter]) -> tuple[list[str], bool]:
    users = {r: [p.path.stem for p in programs if any(w.rule == r for w in p.words)] for r in RULES}
    lines = [f"{'rule':<15}{'lift words':>11}  corpus programs"]
    ok = True
    for r in RULES:
        lift = sum(c[r] for c in lift_words.values())
        flag = ""
        if len(users[r]) < MIN_PROGRAMS_PER_RULE:
            ok, flag = False, "  UNDER-TESTED"
        lines.append(f"{r:<15}{lift:>11}  {len(users[r])} {','.join(users[r])}{flag}")
    return lines, ok


def gate(corpus_dir: Path, lift_files: list[Path], simh_bin: Path, macro1: Path, work: Path) -> int:
    programs = [load(p) for p in sorted(corpus_dir.glob("*.c"))]
    failed = False
    for prog in programs:
        diffs = run_program(prog, simh_bin, macro1, work)
        status = "ok" if not diffs else f"{len(diffs)} DIFFER"
        print(f"  {prog.path.name:<16} {len(prog.inputs):>5} calls  {len(prog.words):>3} words  {status}")
        for d in diffs[:5]:
            print("    " + d)
        failed |= bool(diffs)
    lift_words = {}
    for f in lift_files:
        words = layout.place(dialect.lower_unit(front.parse(f)), "zz")
        lift_words[f.name] = Counter(w.rule for w in words)
    lines, ok = coverage(programs, lift_words)
    print("\n".join("  " + line for line in lines))
    return 1 if failed or not ok else 0
