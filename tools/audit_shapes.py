"""Shape audit of the game's Processors: which bodies are the same once
Record, field, parameter and local names are stripped, and how far each
body could split.

Three shapes per body. Strict keeps which fields share a Record and
keeps constants and enum members. Ports drops the Record grouping: each
Record.field the body touches is one port, as a Processor that names no
Records sees it; two bodies with one ports shape are one Processor wired
to different fields. Loose also abstracts constants and enum members
(one Processor that takes its constants from the Network too).
Statements get the same three shapes, which shows what the pieces would
share if a split reached one statement.

Read-only: it reports, it changes nothing.

Usage: audit_shapes.py [RUNS dir] (default: runs/)."""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import runs

OPERATORS = {"bin", "neg", "not", "call"}
MODES = {
    "strict": "strict (Records, constants and enum members kept apart)",
    "ports": "ports (each Record.field a port; constants kept)",
    "loose": "loose (ports; constants and enum members abstracted)",
}


def unit_of(root: Path) -> dict[str, str]:
    out = {}
    for path in runs.source_files(root):
        for m in re.finditer(r"^processor (\w+)", path.read_text(), re.M):
            out[m[1]] = path.stem
    return out


class Shaper:
    """Renames by first appearance, so equal shapes print equal."""

    def __init__(self, prog: runs.Program, r: runs.Routine, mode: str):
        self.records, self.params = set(prog.records), set(r.params)
        self.ports, self.loose = mode in ("ports", "loose"), mode == "loose"
        self.members = {m for ms in prog.enums.values() for m in ms}
        self.names: dict[tuple[str, str], str] = {}

    def name(self, cls: str, n: str) -> str:
        key = (cls, n)
        if key not in self.names:
            self.names[key] = f"{cls}{sum(1 for k in self.names if k[0] == cls)}"
        return self.names[key]

    def e(self, x) -> str:
        tag = x[0]
        if tag == "name":
            n = x[1]
            if n in self.records:
                return self.name("R", n)
            if n in self.params:
                return self.name("p", n)
            if n in self.members:
                return "E" if self.loose else n
            return self.name("v", n)
        if tag == "num":
            return "K" if self.loose else str(x[1])
        if tag == "bool":
            return "K" if self.loose else str(x[1])
        if tag == "field" and self.ports and x[1][0] == "name" and x[1][1] in self.records:
            return self.name("P", f"{x[1][1]}.{x[2]}")
        if tag == "field":
            return f"{self.e(x[1])}.{self.name('f', x[2])}"
        if tag == "index":
            return f"{self.e(x[1])}[{self.e(x[2])}]"
        if tag == "call":
            return f"{x[1]}({', '.join(self.e(a) for a in x[2])})"
        if tag == "bin":
            return f"({self.e(x[2])} {x[1]} {self.e(x[3])})"
        if tag == "neg":
            return f"-{self.e(x[1])}"
        if tag == "not":
            return f"not {self.e(x[1])}"
        if tag == "tuple":
            return f"({', '.join(self.e(a) for a in x[1])})"
        raise ValueError(x)

    def s(self, st, depth: int = 0) -> list[str]:
        pad, head = "  " * depth, st[0]
        if head in ("let", "set"):
            return [f"{pad}{head} {self.e(st[1])} = {self.e(st[2])}"]
        if head == "if":
            out = []
            for k, (cond, body) in enumerate(st[1]):
                out.append(f"{pad}{'if' if k == 0 else 'elif'} {self.e(cond)}:")
                out += self.block(body, depth + 1)
            if st[2]:
                out.append(f"{pad}else:")
                out += self.block(st[2], depth + 1)
            return out
        if head == "loop":
            return [f"{pad}loop at most {self.e(st[1])}:"] + self.block(st[2], depth + 1)
        if head == "for":
            return [f"{pad}for {self.name('v', st[1])} in {self.e(st[2])}..{self.e(st[3])}:"] + \
                self.block(st[4], depth + 1)
        if head == "jump":
            return [f"{pad}jump {self.e(st[1])} at most {self.e(st[2])}"]
        if head == "emit":
            return [f"{pad}emit {self.name('R', st[1])}: {', '.join(self.e(a) for a in st[2])}"]
        if head == "run":
            return [f"{pad}run {st[1]}({', '.join(self.e(a) for a in st[2])})"]
        if head == "match":
            out = [f"{pad}match {self.e(st[1])}:"]
            for arm, body in st[2].items():
                out.append(f"{pad}  {'E' if self.loose else arm}:")
                out += self.block(body, depth + 2)
            return out
        return [f"{pad}{head}"]

    def block(self, body: list, depth: int = 0) -> list[str]:
        return [line for st in body for line in self.s(st, depth)]


def walk(body: list):
    """Every statement, nested ones too."""
    for st in body:
        yield st
        head = st[0]
        if head == "if":
            for _, b in st[1]:
                yield from walk(b)
            yield from walk(st[2])
        elif head == "loop":
            yield from walk(st[2])
        elif head == "for":
            yield from walk(st[4])
        elif head == "match":
            for b in st[2].values():
                yield from walk(b)


def operators(x) -> int:
    if isinstance(x, tuple):
        if x and isinstance(x[0], str):
            return (x[0] in OPERATORS) + sum(operators(y) for y in x[1:])
        return sum(operators(y) for y in x)
    if isinstance(x, list):
        return sum(operators(y) for y in x)
    if isinstance(x, dict):
        return sum(operators(y) for y in x.values())
    return 0


def leaf(st) -> tuple:
    """A statement without its nested body, for the statement census."""
    head = st[0]
    if head == "if":
        return ("if", [(c, []) for c, _ in st[1]], [], st[-1])
    if head == "loop":
        return ("loop", st[1], [], st[-1])
    if head == "for":
        return ("for", st[1], st[2], st[3], [], st[-1])
    if head == "match":
        return ("match", st[1], {}, st[-1])
    return st


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else runs.source()
    prog = runs.check(runs.load(runs.source_files(root)), sides=False)
    unit = unit_of(root)
    shown = runs.presentation_routines(prog)
    game = sorted(n for n, r in prog.routines.items() if r.kind == "processor" and n not in shown)
    pres = sorted(n for n, r in prog.routines.items() if r.kind == "processor" and n in shown)

    def shape(n: str, mode: str) -> str:
        r = prog.routines[n]
        return "\n".join(Shaper(prog, r, mode).block(r.body))

    stmts = {n: list(walk(prog.routines[n].body)) for n in game}
    ops = {n: operators(prog.routines[n].body) for n in game}

    print(f"# Shape audit of the game Processors ({root})")
    print()
    print(f"Processors: {len(game) + len(pres)}; game {len(game)}, presentation {len(pres)} (left out).")
    print(f"Game statements: {sum(len(s) for s in stmts.values())}; operators: {sum(ops.values())}.")

    by_unit = defaultdict(list)
    for n in game:
        by_unit[unit[n]].append(n)
    print()
    print("## Per unit")
    print()
    print(f"{'unit':16} {'procs':>5} {'stmts':>5} {'ops':>5} {'1-stmt':>6}")
    for u, ns in sorted(by_unit.items()):
        print(f"{u:16} {len(ns):5} {sum(len(stmts[n]) for n in ns):5} {sum(ops[n] for n in ns):5} "
              f"{sum(1 for n in ns if len(stmts[n]) == 1):6}")

    print()
    print("## Split depth: statements per Processor")
    print()
    hist = defaultdict(int)
    for n in game:
        hist[len(stmts[n])] += 1
    for k in sorted(hist):
        print(f"{k:3} statements: {hist[k]:3} Processors  {'#' * hist[k]}")

    unit_pairs: dict[tuple[str, str], int] = defaultdict(int)
    for mode, label in MODES.items():
        clusters = defaultdict(list)
        for n in game:
            clusters[shape(n, mode)].append(n)
        shared = sorted((ms for ms in clusters.values() if len(ms) > 1), key=lambda ms: (-len(ms), ms))
        print()
        print(f"## Whole-Processor clusters, {label}")
        print()
        print(f"{len(clusters)} distinct shapes for {len(game)} Processors; "
              f"{len(shared)} shared by {sum(len(ms) for ms in shared)} Processors "
              f"(one file each would save {sum(len(ms) - 1 for ms in shared)}).")
        for ms in shared:
            units = sorted({unit[m] for m in ms})
            if mode == "ports":
                for a, b in combinations(units, 2):
                    unit_pairs[a, b] += 1
            print()
            print(f"- {len(ms)} × [{', '.join(units)}]: {', '.join(ms)}")
            for line in shape(ms[0], mode).splitlines():
                print(f"      {line}")

    print()
    print("## Units sharing whole-Processor shapes (ports)")
    print()
    cross = sorted(unit_pairs.items(), key=lambda kv: -kv[1])
    if not cross:
        print("No shape spans two units.")
    for (a, b), k in cross:
        print(f"- {a} & {b}: {k} shapes")

    for mode in MODES:
        census = defaultdict(list)
        for n in game:
            for st in stmts[n]:
                r = prog.routines[n]
                census["\n".join(Shaper(prog, r, mode).s(leaf(st)))].append(n)
        total = sum(len(v) for v in census.values())
        shared = sorted(((k, v) for k, v in census.items() if len(v) > 1), key=lambda kv: -len(kv[1]))
        print()
        print(f"## Statement census, {mode}")
        print()
        print(f"{total} statements, {len(census)} distinct shapes; {len(shared)} shapes recur, "
              f"covering {sum(len(v) for _, v in shared)} statements. Top 25:")
        for k, v in shared[:25]:
            units = sorted({unit[m] for m in v})
            print(f"- {len(v):3} × {k.splitlines()[0]}   [{', '.join(units)}]")

    print()
    print("## Every game Processor")
    print()
    print(f"{'processor':28} {'unit':16} {'stmts':>5} {'ops':>4}")
    for n in sorted(game, key=lambda n: (unit[n], n)):
        print(f"{n:28} {unit[n]:16} {len(stmts[n]):5} {ops[n]:4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
