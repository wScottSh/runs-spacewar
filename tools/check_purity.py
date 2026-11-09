"""The purity report: every place the RUNS text is not yet pure, one line
each, then the count. The conversion is done when the count is 0; from then
on runs.check refuses every impurity of kind.

A Record of instructions that a Processor runs with `jump` is code kept as
data. RUNS keeps `jump` for machine glitches, where play runs data as code;
Spacewar has none (INTENT.md), so in Spacewar it is the original's way of
drawing and counts as impure here.

With --against REF (a commit, such as HEAD), it also compares with the
report at REF and fails on any line REF did not have, unless the line names
a Processor or Network that touches a Record which had no kind at REF and
has one now: giving a Record its kind reveals impurities that were already
there, and nothing else may add one.

Usage: check_purity.py [RUNS dir] [--against REF] (default: runs/)."""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import runs


def report(root: Path) -> tuple[runs.Program, list[str]]:
    prog = runs.check(runs.load(sorted(root.glob("*.runs")) + sorted(root.glob("*.runs-prim"))), sides=False)
    found = runs.impurities(prog)
    found += [f"{r.name}.{f}: a Record holds data; instructions a Processor runs are logic"
              for r in prog.records.values() for f, (typ, _) in r.fields.items() if typ == "insn"]
    found += [f"processor {r.name}: runs instructions from a Record (jump); its logic belongs in its own text"
              for r in prog.routines.values()
              if r.kind == "processor" and any(s[0] == "jump" for s in runs.walk_statements(r.body))]
    return prog, found


def at(ref: str, root: Path, out: Path) -> Path:
    rel = root.resolve().relative_to(Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()))
    for name in subprocess.check_output(["git", "ls-tree", "--name-only", f"{ref}:{rel}"], text=True).split():
        (out / name).write_text(subprocess.check_output(["git", "show", f"{ref}:{rel}/{name}"], text=True))
    return out


def main() -> int:
    args = sys.argv[1:]
    ref = None
    if "--against" in args:
        i = args.index("--against")
        ref = args[i + 1]
        del args[i:i + 2]
    root = Path(args[0]) if args else runs.source()
    prog, found = report(root)
    for line in found:
        print(line)
    print(f"impurities: {len(found)}")
    if ref is None:
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        before_prog, before = report(at(ref, root, Path(tmp)))
    typed_now = {n for n, r in prog.records.items()
                 if r.side and n in before_prog.records and not before_prog.records[n].side}
    revealed = lambda line: (m := re.match(r"(?:processor|network) (\w+)", line)) and \
        (prog.routines[m[1]].reads | prog.routines[m[1]].writes | runs.mentions(prog.routines[m[1]].body, set(prog.records))) & typed_now
    new = [line for line in found if line not in set(before) and not revealed(line)]
    gone = [line for line in before if line not in set(found)]
    print(f"against {ref}: {len(before)} before, {len(gone)} gone, {len(new)} new")
    for line in new:
        print(f"  new: {line}")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
