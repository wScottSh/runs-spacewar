"""Every order a graph allows, and which of them compile to the original
program. For "Order between independent transitions" (#63).

A graph allows an order when each transition comes after the transitions that
write the places it reads (its inputs and its guard's place), and each branch
of a test stays one block. The stored source (places sharing PDP-1 words)
adds one more condition: no word is overwritten before its value's last read
(graph.hazards). For each allowed order this module emits the stored source,
splices it into a scratch copy of runs/, and runs runsc. It records the
result: identical to the original, the first differing address, or runsc's
refusal, and the number of words in the image."""
from __future__ import annotations

import itertools
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import graph  # noqa: E402
import arith  # noqa: E402


@dataclass
class Outcome:
    order: tuple[str, ...]
    hazard: str | None = None      # the stored source overwrites a word before its read
    refused: str | None = None     # runsc's error
    differs: str | None = None     # "00172 want 260200 got 260173"
    words: int | None = None       # words in the assembled image

    @property
    def identical(self) -> bool:
        return not (self.hazard or self.refused or self.differs)

    def verdict(self) -> str:
        if self.hazard:
            return f"storage hazard: {self.hazard}"
        if self.refused:
            return f"runsc refuses: {self.refused}"
        if self.differs:
            return f"differs at {self.differs} ({self.words} words)"
        return f"identical to the original ({self.words} words)"


def units(g: graph.Graph) -> tuple[list[str], dict[str, list[list[str]]]]:
    """Unguarded transitions, and each test's branches: test place -> one
    list of transitions per side (the test first, else last)."""
    guard = graph.guards(g)
    plain = [t for t in g.transitions if guard[t] is None]
    tests: dict[str, dict[str, list[str]]] = {}
    for t in g.transitions:
        if guard[t]:
            tests.setdefault(guard[t][0], {}).setdefault(guard[t][1], []).append(t)
    return plain, {p: [sides[k] for k in sorted(sides, key=lambda k: k == "else")] for p, sides in tests.items()}


def depends(g: graph.Graph) -> dict[str, set[str]]:
    """t -> the transitions that write a place t reads."""
    guard = graph.guards(g)
    writers: dict[str, set[str]] = {}
    for a in g.arcs:
        if not a.into:
            writers.setdefault(a.place, set()).add(a.transition)
    out = {t: set() for t in g.transitions}
    for a in g.arcs:
        if a.into:
            out[a.transition] |= writers.get(a.place, set())
    for t in g.transitions:
        if guard[t]:
            out[t] |= writers.get(guard[t][0], set())
    return out


def linear_extensions(nodes: list[str], before: dict[str, set[str]]):
    """Every order of nodes in which each comes after all of before[n]."""
    def go(done: tuple[str, ...], left: frozenset[str]):
        if not left:
            yield done
            return
        for n in sorted(left):
            if before[n] <= set(done):
                yield from go(done + (n,), left - {n})
    yield from go((), frozenset(nodes))


def allowed(g: graph.Graph):
    """Every order the graph allows: the units in each order their
    dependencies permit, each branch's members in each order theirs permit."""
    plain, tests = units(g)
    dep = depends(g)
    member = {t: p for p, sides in tests.items() for side in sides for t in side}
    unit = lambda t: member.get(t, t)  # noqa: E731
    nodes = plain + list(tests)
    before = {n: set() for n in nodes}
    for t, ds in dep.items():
        for d in ds:
            if unit(d) != unit(t):
                before[unit(t)].add(unit(d))
    inner = {p: [list(linear_extensions(side, {t: dep[t] & set(side) for t in side})) for side in sides]
             for p, sides in tests.items()}
    for outer in linear_extensions(nodes, before):
        choices = [itertools.product(*inner[n]) if n in tests else [((n,),)] for n in outer]
        for picked in itertools.product(*choices):
            yield tuple(t for sides in picked for side in sides for t in side)


def hazards(g: graph.Graph, order, at) -> list[str]:
    """../graph.py's hazards, walked on every path: one side of each test.
    A guard's place is read once, by the test, before its block."""
    guard = graph.guards(g)
    tests = sorted({guard[t][0] for t in order if guard[t]})
    sides = {p: sorted({guard[t] for t in order if guard[t] and guard[t][0] == p}) for p in tests}
    bad = []
    for path in itertools.product(*sides.values()):
        taken = set(path)
        holds: dict[str, str] = {}
        opened = None

        def read(t, place):
            if place.startswith(graph.BOUNDARY + ".") and at(place) not in holds:
                return
            if holds.get(at(place), place) != place:
                bad.append(f"{t} reads {place}, but {at(place)} holds {holds[at(place)]}")
        for t in order:
            if guard[t] and guard[t] not in taken:
                continue
            if guard[t] and guard[t] != opened:
                read(t, guard[t][0])
            opened = guard[t]
            bundle = g.transitions[t] if g.transitions[t] in arith.BUNDLES else None
            for a in g.arcs:
                if a.transition == t and a.into and a.io:
                    read(t, a.place)
            for a in g.arcs:
                if a.transition == t and a.into and a.io and bundle:   # copied into the bundle's word
                    holds[at.word(f"{bundle}_call.{a.io}")] = a.place
            for a in g.arcs:
                if a.transition == t and not a.into:
                    if bundle:                                          # and out of it
                        holds[at.word(f"{bundle}_call.{a.io}")] = a.place
                    holds[at(a.place)] = a.place
    return bad


WORD = re.compile(r"^\s*\d+ [0-7]{5} [0-7]{6}", re.M)
BUILT: dict[tuple[bool, str], Outcome] = {}   # (files reversed, source) -> what runsc made of it


def source_of(g: graph.Graph, sigs, order, r: arith.Routine) -> tuple[str | None, str | None]:
    """The stored source for an order, or the first storage hazard."""
    graph.BOUNDARY = r.call
    at = arith.Storage(g, sigs, True, r.call)
    if bad := hazards(g, list(order), at):
        return None, bad[0]
    return arith.emit(g, sigs, list(order), at), None


def compile_order(g: graph.Graph, sigs, order, r: arith.Routine) -> Outcome:
    source, hazard = source_of(g, sigs, order, r)
    if hazard:
        return Outcome(order, hazard=hazard)
    if (arith.REVERSED, source) in BUILT:
        o = BUILT[arith.REVERSED, source]
        return Outcome(order, o.hazard, o.refused, o.differs, o.words)
    BUILT[arith.REVERSED, source] = out = build(source, order, r)
    return out


def build(source: str, order, r: arith.Routine) -> Outcome:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        arith.splice(tmp, r, source, shared=True)
        graph.runsc.BINDINGS = tmp / "pdp1"
        try:
            graph.runsc.build(graph.runs.program(tmp / "runs"), tmp / "out")
        except Exception as e:  # runsc's refusals are BindError, the evaluator's RunsError
            return Outcome(order, refused=str(e).splitlines()[0][:160])
        said = graph.runsc.build.said
        if m := re.search(r"error: (.*)", said):
            return Outcome(order, refused=m[1][:160])
        lst = tmp / "out/build/lift/program.lst"
        words = len(WORD.findall(lst.read_text())) if lst.exists() else None
        if "identical to the original" in said:
            return Outcome(order, words=words)
        m = re.search(r"first difference at ([0-7]+): want ([0-7]+) got ([0-7]+)", said)
        return Outcome(order, differs=f"{m[1]} want {m[2]} got {m[3]}" if m else said.strip().splitlines()[-1],
                       words=words)
