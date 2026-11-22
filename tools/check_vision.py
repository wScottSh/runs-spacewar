"""The vision report: how far the RUNS source stands from the EGS vision
(../.github/GLOSSARY.md), file by file. It reports and gates nothing: it
always exits 0 once the source loads, and check_all.sh does not run it.

It reads the loaded Program (runs.load, then runs.check without sides, as
check_purity.py does) and counts five distances, each defined in HEADER.
Every finding prints as one line, then a table of the counts per file and
the totals.

Usage: check_vision.py [RUNS dir] (default: runs/)."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import runs

HEADER = """\
# The distances from the vision, counted per file (GLOSSARY.md is ../.github/GLOSSARY.md).
#
# names_records     Processors that name Records (GLOSSARY.md 166-169: a Processor knows nothing
#                   of the Records it is wired to). A Processor counts when it names any Record:
#                   in `reads:`, `writes:`, `requires:`, or its body.
# control_flow      Networks written as control flow rather than wiring (GLOSSARY.md 162-199:
#                   the explicit wiring of Records to Processors; order derived, never authored).
#                   A Network counts when its body holds anything but runs that wire each input
#                   and output to a Field: a run that passes a slot or nothing, `if`, `match`,
#                   `loop`, `for`, `break`, `stop`, `wait`, `unreachable`.
# mid_exit          Loops with a mid-body exit (GLOSSARY.md 204-206, 344-347: the count is fixed
#                   before the loop; no break, continue or early return). Each `loop` or `for`, in
#                   a Processor or a Network, counts once when its body holds a `break` or
#                   `continue` that leaves it (not one that leaves a loop inside it), or any
#                   `return` or `stop`.
# open_guards       Guard sets that do not cover every case (GLOSSARY.md 351-358: exactly one
#                   guard true, always; an open-typed value needs an explicit else). Each `if` in
#                   a Network with no `else`. A `match` never counts: runs.check refuses one
#                   without an arm for each member of its enum. A Processor's `if` is not a guard
#                   (GLOSSARY.md 359-370) and does not count.
# extra_processors  Files holding more than one Processor: each file's Processors beyond its
#                   first. A file holds more than one when its count is above 0.
#
# A Record a Processor changes in place is no distance: only a Processor changes a Record, and it
# may put its result back in the same place (GLOSSARY.md 88-93); tools/graph.py refuses two
# transitions that write one place unless the wiring orders them.
#
# A network file is wiring with guards, so it counts nothing under control_flow, mid_exit
# and open_guards; tools/graph.py refuses one whose guards on a place are not one test and
# its else. A loop bundle's cycle (GLOSSARY.md 196-206) is legal and counts nothing: tools/graph.py
# refuses any cycle that does not run through one counter a count_down takes a token from
# each pass. A `for` or `loop` in a Network written as structured code counts under
# control_flow.
"""

COUNTS = ("names_records", "control_flow", "mid_exit", "open_guards", "extra_processors")


def program(root: Path) -> tuple[runs.Program, list[Path]]:
    paths = runs.source_files(root)
    return runs.check(runs.load(paths), sides=False), paths


class Home:
    """Which file declares each Record and each routine, from the parser's
    lines. A Record and a Network may share a name (frame), so each kind
    has its own map."""

    def __init__(self, paths: list[Path]):
        self.records: dict[str, str] = {}
        self.routines: dict[str, str] = {}
        for path in paths:
            for line in runs.lines(path):
                t = line.toks
                if t[0] in runs.SIDES and len(t) > 1:
                    t = t[1:]
                if t[0] in ("record", "stream"):
                    self.records[t[1]] = path.name
                elif t[0] in ("processor", "network"):
                    self.routines[t[1]] = path.name

    def __getitem__(self, name: str) -> str:
        return self.routines[name]


def as_written(prog: runs.Program) -> dict[str, runs.Routine]:
    """The routines the source writes: every routine but the copies a wired run
    makes and the Networks lowered from network files."""
    return {**{n: r for n, r in prog.routines.items() if n not in prog.copies and n not in prog.graphs},
            **prog.templates}


def names_records(prog, routines, home) -> list[tuple[str, str]]:
    records = set(prog.records)
    out = []
    for r in routines.values():
        if r.kind == "processor":
            named = r.reads | r.writes | runs.mentions(r.body, records) | runs.mentions(r.requires, records)
            if named:
                out.append((home[r.name], f"names_records {r.name}: {', '.join(sorted(named))}"))
    return out


CONTROL = ("if", "match", "loop", "for", "break", "stop", "wait", "unreachable")


def control_flow(prog, routines, home) -> list[tuple[str, str]]:
    out = []
    for r in routines.values():
        if r.kind != "network":
            continue
        ops = Counter()
        for s in runs.walk_statements(r.body):
            if s[0] in CONTROL:
                ops[s[0]] += 1
            elif s[0] == "run" and s[1] not in prog.copies:
                ops["run"] += 1
        if ops:
            out.append((home[r.name], f"control_flow {r.name}: "
                        + ", ".join(f"{op} {n}" for op, n in sorted(ops.items()))))
    return out


def exits(stmts: list, depth: int) -> list[str]:
    """The exits in stmts that leave the loop `depth` loops out from them."""
    found = []
    for s in stmts:
        op = s[0]
        if op in ("break", "continue") and depth == 0 or op in ("return", "stop"):
            found.append(op)
        elif op == "if":
            for _, body in s[1]:
                found += exits(body, depth)
            found += exits(s[2], depth)
        elif op == "match":
            for body in s[2].values():
                found += exits(body, depth)
        elif op in ("loop", "for"):
            found += exits(s[-2], depth + 1)
    return found


def mid_exit(prog, routines, home) -> list[tuple[str, str]]:
    out = []
    for r in routines.values():
        for s in runs.walk_statements(r.body):
            if s[0] in ("loop", "for") and (found := exits(s[-2], 0)):
                out.append((home[r.name], f"mid_exit {r.kind} {r.name}: {s[0]} at {Path(s[-1]).name}: "
                            + ", ".join(f"{op} {n}" for op, n in sorted(Counter(found).items()))))
    return out


def open_guards(prog, routines, home) -> list[tuple[str, str]]:
    out = []
    for r in routines.values():
        if r.kind != "network":
            continue
        for s in runs.walk_statements(r.body):
            at = Path(s[-1]).name
            if s[0] == "if" and not s[2]:
                out.append((home[r.name], f"open_guards {r.name}: if at {at} has no else"))
    return out


def extra_processors(prog, routines, home) -> list[tuple[str, str]]:
    per_file: dict[str, list[str]] = {}
    for r in routines.values():
        if r.kind == "processor":
            per_file.setdefault(home[r.name], []).append(r.name)
    return [(f, f"extra_processors {f}: {name}") for f, names in sorted(per_file.items()) for name in names[1:]]


def report(root: Path) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Every finding as (count, file, line), and the files in load order."""
    prog, paths = program(root)
    home = Home(paths)
    routines = as_written(prog)
    found = []
    for name in COUNTS:
        found += [(name, f, line) for f, line in globals()[name](prog, routines, home)]
    return found, [p.name for p in paths]


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else runs.source()
    found, files = report(root)
    print(HEADER)
    for _, _, line in found:
        print(line)
    table = Counter((c, f) for c, f, _ in found)
    width = max(len(f) for f in files + ["total"])
    print()
    print(f"{'file':<{width}}  " + "  ".join(COUNTS))
    for f in files + ["total"]:
        cells = [sum(table[c, x] for x in files) if f == "total" else table[c, f] for c in COUNTS]
        print(f"{f:<{width}}  " + "  ".join(f"{n:>{len(c)}}" for n, c in zip(cells, COUNTS)))
    shared = sum(1 for f in files if table["extra_processors", f])
    print(f"\nfiles holding more than one Processor: {shared}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
