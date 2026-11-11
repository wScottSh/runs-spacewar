"""The vision report: how far the RUNS source stands from the EGS vision
(../.github/CONTEXT.md), file by file. It reports and gates nothing: it
always exits 0 once the source loads, and check_all.sh does not run it.

It reads the loaded Program (runs.load, then runs.check without sides, as
check_purity.py does) and counts six distances, each defined in HEADER.
Every finding prints as one line, then a table of the counts per file and
the totals.

Usage: check_vision.py [RUNS dir] (default: runs/)."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import runs

HEADER = """\
# The distances from the vision, counted per file (CONTEXT.md is ../.github/CONTEXT.md).
#
# in_place          Records written in place (CONTEXT.md 90-92: write once, never overwrite).
#                   A Record counts once when any of its Fields is set at two or more `set`
#                   statements across the Processors, or a Processor sets it after reading the
#                   value it held (read before the set, or read in a loop that sets it).
#                   Counted in the file that declares the Record. A stream is not counted:
#                   `emit` adds a fresh entry.
# names_records     Processors that name Records (CONTEXT.md 166-169: a Processor knows nothing
#                   of the Records it is wired to). A Processor counts when it names any Record:
#                   in `reads:`, `writes:`, `requires:`, or its body.
# control_flow      Networks written as control flow rather than wiring (CONTEXT.md 162-199:
#                   the explicit wiring of Records to Processors; order derived, never authored).
#                   A Network counts when its body holds anything but runs that wire each input
#                   and output to a Field: a run that passes a slot or nothing, `if`, `match`,
#                   `loop`, `for`, `break`, `stop`, `wait`, `unreachable`.
# mid_exit          Loops with a mid-body exit (CONTEXT.md 204-206, 344-347: the count is fixed
#                   before the loop; no break, continue or early return). Each `loop` or `for`, in
#                   a Processor or a Network, counts once when its body holds a `break` or
#                   `continue` that leaves it (not one that leaves a loop inside it), or any
#                   `return` or `stop`.
# open_guards       Guard sets that do not cover every case (CONTEXT.md 351-358: exactly one
#                   guard true, always; an open-typed value needs an explicit else). Each `if` in
#                   a Network with no `else`. A `match` never counts: runs.check refuses one
#                   without an arm for each member of its enum. A Processor's `if` is not a guard
#                   (CONTEXT.md 359-370) and does not count.
# extra_processors  Files holding more than one Processor: each file's Processors beyond its
#                   first. A file holds more than one when its count is above 0.
"""

COUNTS = ("in_place", "names_records", "control_flow", "mid_exit", "open_guards", "extra_processors")


def program(root: Path) -> tuple[runs.Program, list[Path]]:
    paths = sorted(root.glob("*.runs")) + sorted(root.glob("*.runs-prim"))
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
    """The routines the source writes: every routine but the copies a wired run makes."""
    return {**{n: r for n, r in prog.routines.items() if n not in prog.copies}, **prog.templates}


def field_of(e, records) -> tuple[str, str] | None:
    base = e[1] if e[0] == "index" else e
    if base[0] == "field" and base[1][0] == "name" and base[1][1] in records:
        return base[1][1], base[2]
    return None


def fields_read(tree, records, out: set) -> None:
    """The Record Fields an expression or statement tree reads. A `set` target
    is written, not read (its slot expression is read). Building an
    instruction reads only its operand's slot expression, as runs.mentions."""
    if isinstance(tree, tuple) and tree:
        op = tree[0]
        if op in ("set", "let") and len(tree) == 4:
            for t in tree[1][1] if tree[1][0] == "tuple" else [tree[1]]:
                if t[0] == "index":
                    fields_read(t[2], records, out)
            fields_read(tree[2], records, out)
            return
        if op == "field" and (f := field_of(tree, records)):
            out.add(f)
            return
        if op == "call" and runs.instruction_call(tree[1], tree[2]):
            if tree[2] and tree[2][0][0] == "index":
                fields_read(tree[2][0][2], records, out)
            return
    if isinstance(tree, (list, tuple)):
        for t in tree:
            fields_read(t, records, out)
    elif isinstance(tree, dict):
        fields_read(list(tree.values()), records, out)


def fields_set(stmts: list, records) -> list[tuple[str, str]]:
    """Each Record Field a `set` writes, once a statement that writes it."""
    return [f for s in runs.walk_statements(stmts) if s[0] in ("set", "let")
            for t in (s[1][1] if s[1][0] == "tuple" else [s[1]]) if (f := field_of(t, records))]


def held_reads(stmts: list, records, done: set) -> tuple[set, set]:
    """The Fields stmts read while they still hold the value from before the
    Processor ran: read before any set of them on the way there, or read in
    a loop that sets them (the next pass reads what this one set). Returns
    those, and the Fields set on every way through stmts."""
    found: set = set()

    def read(e) -> None:
        got: set = set()
        fields_read(e, records, got)
        found.update(got - done)

    for s in stmts:
        op = s[0]
        if op in ("set", "let"):
            read(s)
            done = done | set(fields_set([s], records))
        elif op in ("if", "match"):
            read([c for c, _ in s[1]] if op == "if" else s[1])
            arms = [b for _, b in s[1]] + [s[2]] if op == "if" else list(s[2].values())
            after = []
            for body in arms:
                got, d = held_reads(body, records, done)
                found |= got
                after.append(d)
            done = set.intersection(*after) if after else done
        elif op in ("loop", "for"):
            read(list(s[1:-2]))
            looped: set = set()
            fields_read(s[-2], records, looped)
            found |= looped & set(fields_set(s[-2], records))
            found |= held_reads(s[-2], records, done)[0]
        elif op == "emit":
            read(s[2])
    return found, done


def in_place(prog, routines, home) -> list[tuple[str, str]]:
    records = {n for n, r in prog.records.items() if not r.stream}
    sites: dict[tuple[str, str], list[str]] = {}
    updates: dict[tuple[str, str], set[str]] = {}
    for r in routines.values():
        if r.kind != "processor":
            continue
        read = held_reads(r.body, records, set())[0]
        for f in fields_set(r.body, records):
            sites.setdefault(f, []).append(r.name)
            if f in read:
                updates.setdefault(f, set()).add(r.name)
    by_record: dict[str, list[str]] = {}
    for f, who in sorted(sites.items()):
        if len(who) > 1 or f in updates:
            why = []
            if len(who) > 1:
                why.append(f"{len(who)} sets by {', '.join(sorted(set(who)))}")
            if f in updates:
                why.append(f"updated by {', '.join(sorted(updates[f]))}")
            by_record.setdefault(f[0], []).append(f"{f[1]} ({'; '.join(why)})")
    return [(home.records.get(rec) or home[prog.records[rec].owner], f"in_place {rec}: {', '.join(fs)}")
            for rec, fs in sorted(by_record.items())]


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
