"""Shared by the three graph formats of "How a Network is written as a literal
graph" (#56). Each format's load.py parses its network file into a Graph; this
module does the rest, the same for all three:

  check     every input and output wired once, every place a Record field,
            each place written once (or once per branch), an else beside each guard
  schedule  the order, derived from the wiring
  emit      today's RUNS source for the order, two ways: every place its own
            field (the Evaluator runs it) and places sharing PDP-1 words
            (runsc compiles it)
  verify    both in a scratch copy of runs/ and pdp1/: check_multiply's SIMH
            cases in the Evaluator, and runsc's image against the original's

Nothing under runs/, pdp1/ or tools/ changes."""
from __future__ import annotations

import os
import random
import re
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import runs, runsc  # noqa: E402


@dataclass(frozen=True)
class Arc:
    place: str                 # record.field
    transition: str
    io: str | None             # the Processor's input or output; None on a guard arc
    into: bool                 # place -> transition
    guard: str | None = None   # "< 0", or "else"; only on a guard arc


@dataclass
class Graph:
    name: str
    places: list[str]
    transitions: dict[str, str]    # transition -> Processor
    arcs: list[Arc]


@dataclass
class Signature:
    inputs: list[str]              # in and inout, in the file's order
    outputs: list[str]             # out and inout
    inout: set[str] = field(default_factory=set)


EXTRA: list[Path] = []      # more Processor and Record files (the unrolled loop's)


def files(sub: str, pattern: str) -> list[Path]:
    return sorted((HERE / sub).glob(pattern)) + [f for d in EXTRA for f in sorted(d.glob(pattern))]


def signatures() -> dict[str, Signature]:
    sigs = {}
    for f in files("processors", "*.runs-prim"):
        lines = f.read_text().splitlines()
        name = lines[0].split()[1]
        s = Signature([], [])
        for line in lines[1:]:
            m = re.match(r"\s+(in|out|inout) (\w+):", line)
            if m:
                d, n = m.groups()
                if d in ("in", "inout"): s.inputs.append(n)
                if d in ("out", "inout"): s.outputs.append(n)
                if d == "inout": s.inout.add(n)
        sigs[name] = s
    return sigs


def record_fields() -> dict[str, list[str]]:
    out = {}
    for f in files("records", "*.runs"):
        rec = None
        for line in f.read_text().splitlines():
            if m := re.match(r"\w+ record (\w+)", line):
                rec = m.group(1); out[rec] = []
            elif rec and (m := re.match(r"\s+(\w+):", line)):
                out[rec].append(m.group(1))
    return out


BOUNDARY = "multiply_call"


def check(g: Graph, sigs: dict[str, Signature]) -> None:
    fields = {f"{r}.{f}" for r, fs in record_fields().items() for f in fs}
    assert set(g.places) <= fields, f"not a Record field: {sorted(set(g.places) - fields)}"
    used = {a.place for a in g.arcs}
    assert used == set(g.places), f"places stated and wired differ: {sorted(used ^ set(g.places))}"
    for t, p in g.transitions.items():
        s = sigs[p]
        ins = sorted(a.io for a in g.arcs if a.transition == t and a.into and a.io)
        outs = sorted(a.io for a in g.arcs if a.transition == t and not a.into)
        assert ins == sorted(s.inputs), f"{t}: inputs wired {ins}, {p} has {s.inputs}"
        assert outs == sorted(s.outputs), f"{t}: outputs wired {outs}, {p} has {s.outputs}"
    guard = guards(g)
    for place in g.places:
        writers = [a.transition for a in g.arcs if a.place == place and not a.into]
        branches = [guard[w] for w in writers]
        assert len(branches) == len(set(branches)), f"{place} written twice: {writers}"
        assert len(writers) < 2 or all(b for b in branches), f"{place}: an unguarded writer beside a guarded one"
    on = {}
    for a in g.arcs:
        if a.guard:
            on.setdefault(a.place, set()).add(a.guard)
    for place, gs in on.items():
        assert "else" in gs and len(gs) == 2, f"{place}: the guards {sorted(gs)} are not one test and its else"


def guards(g: Graph) -> dict[str, tuple[str, str] | None]:
    """A transition's guard: on its own guard arc, else the guard of the one
    branch that writes its inputs (a token there only on that branch)."""
    own = {a.transition: (a.place, a.guard) for a in g.arcs if a.guard}
    out: dict[str, tuple[str, str] | None] = {}

    def of(t: str):
        if t not in out:
            out[t] = own.get(t)
            if out[t] is None:
                for a in g.arcs:
                    if a.transition == t and a.into and a.io:
                        ws = {of(w.transition) for w in g.arcs if w.place == a.place and not w.into}
                        if len(ws) == 1 and (w := ws.pop()):
                            out[t] = w
        return out[t]
    for t in g.transitions:
        of(t)
    return out


def schedule(g: Graph, sigs: dict[str, Signature]) -> list[str]:
    """Depth-first from the boundary's outputs: a transition after the
    transitions that write its inputs, in the order its Processor lists them,
    then the one that writes its guard's place. Nothing in the network file's
    order enters."""
    guard = guards(g)
    done: list[str] = []

    def writers(place: str) -> list[str]:
        ws = [a.transition for a in g.arcs if a.place == place and not a.into]
        return sorted(ws, key=lambda w: (guard[w] is not None and guard[w][1] == "else", guard[w] or ("", "")))

    def visit(t: str) -> None:
        if t in done:
            return
        wired = {a.io: a.place for a in g.arcs if a.transition == t and a.into and a.io}
        for i in sigs[g.transitions[t]].inputs:
            for w in writers(wired[i]):
                visit(w)
        if guard[t]:
            for w in writers(guard[t][0]):
                visit(w)
        done.append(t)
    for place in sorted(p for p in g.places if p.startswith(BOUNDARY + ".")):
        for w in writers(place):
            visit(w)
    # each branch as one block, at its first member
    order, emitted = [], set()
    for t in done:
        if t in emitted:
            continue
        if guard[t] is None:
            order.append(t); emitted.add(t); continue
        place = guard[t][0]
        for side in sorted({guard[u] for u in done if guard[u] and guard[u][0] == place}, key=lambda x: x[1] == "else"):
            block = [u for u in done if guard[u] == side]
            order += block; emitted |= set(block)
    return order


class Storage:
    """Where a place lives. Written once: each place its own field. Stored:
    a place shares a word with the place an inout replaces, or with the field
    storage.toml names; any other place in the work Record is a register value
    (owned scratch of the Network, which runsc keeps in AC or IO)."""
    def __init__(self, g: Graph, sigs: dict[str, Signature], shared: bool):
        self.shared = shared
        parent = {p: p for p in g.places}

        def find(p):
            while parent[p] != p:
                p = parent[p]
            return p
        for t, proc in g.transitions.items():
            for n in sigs[proc].inout:
                a, b = sorted(find(a.place) for a in g.arcs if a.transition == t and a.io == n)
                # the boundary field is the root; else the first name
                if b.startswith(BOUNDARY + "."):
                    a, b = b, a
                parent[b] = a
        table = tomllib.loads((HERE / "storage.toml").read_text())
        self.where = {}
        for p in g.places:
            r = find(p)
            if r.startswith(BOUNDARY + "."):
                self.where[p] = r
            elif r in table or p in table:
                self.where[p] = table.get(r) or table[p]
            else:
                self.where[p] = r.split(".")[1]
        self.owned = sorted({w for w in self.where.values() if "." not in w})

    def __call__(self, place: str) -> str:
        return self.where[place] if self.shared else place


def emit(g: Graph, sigs: dict[str, Signature], order: list[str], at: Storage) -> str:
    guard = guards(g)
    records = sorted({p.split(".")[0] for p in g.places} if not at.shared else {BOUNDARY})
    out = [f"network {g.name}", f"  writes: {', '.join(records)}"]
    out += [f"  owns {n}: word" for n in at.owned] if at.shared else []
    opened = None
    for t in order:
        proc, s = g.transitions[t], sigs[g.transitions[t]]
        wire = {}
        for a in g.arcs:
            if a.transition == t and a.io:
                wire.setdefault(a.io, {})["in" if a.into else "out"] = at(a.place)
        if proc == "copy" and wire["source"]["in"] == wire["target"]["out"]:
            continue                                      # the value is already there
        if guard[t] != opened:
            if guard[t] is None:
                pass
            elif guard[t][1] == "else":
                out.append("  else:")
            else:
                out.append(f"  if {at(guard[t][0])} {guard[t][1]}:")
            opened = guard[t]
        pad = "    " if guard[t] else "  "
        lines = []
        for n in s.inputs + [o for o in s.outputs if o not in s.inout]:
            w = wire[n]
            if n in s.inout and w["in"] != w["out"]:   # a fresh place for the new value
                out += [f"{pad}run copy", f"{pad}  source: {w['in']}", f"{pad}  target: {w['out']}"]
            lines.append(f"{pad}  {n}: {w.get('out', w.get('in'))}")
        out += [f"{pad}run {proc}"] + lines
    return "\n".join(out) + "\n"


def hazards(g: Graph, order: list[str], at: Storage) -> list[str]:
    """With places sharing words, a place must still hold its value when it is
    read: no place sharing its word is written between. Branches are walked
    one at a time."""
    guard = guards(g)
    bad = []
    for side in {guard[t] for t in order if guard[t]} | {None}:
        holds: dict[str, str] = {}
        for t in order:
            if guard[t] not in (None, side):
                continue
            for a in g.arcs:
                if a.transition == t and a.into:
                    if a.place.startswith(BOUNDARY + ".") and at(a.place) not in holds:
                        continue
                    if holds.get(at(a.place), a.place) != a.place:
                        bad.append(f"{t} reads {a.place}, but {at(a.place)} holds {holds[at(a.place)]}")
            for a in g.arcs:
                if a.transition == t and not a.into:
                    holds[at(a.place)] = a.place
    return bad


def splice(tmp: Path, network: str, work_record: bool) -> None:
    shutil.copytree(ROOT / "runs", tmp / "runs")
    shutil.copytree(ROOT / "pdp1", tmp / "pdp1")
    prim = tmp / "runs/arithmetic.runs-prim"
    t = prim.read_text()
    start, end = t.index("processor multiply  "), t.index("# BBN integer multiply (imp)")
    prim.write_text(t[:start] + network + "\n" + t[end:])
    sw = tmp / "runs/spacewar.runs"
    t = sw.read_text()
    m = re.search(r"game record multiply_call\n(  .*\n)+", t)
    sw.write_text(t[:m.start()] + t[m.end():])
    for f in files("processors", "*.runs-prim"):
        shutil.copy(f, tmp / "runs" / f.name)
    for f in files("records", "*.runs"):
        if work_record or f.stem == BOUNDARY:
            shutil.copy(f, tmp / "runs" / f.name)


def evaluator(tmp: Path, n: int) -> int:
    os.environ["RUNS_SOURCE"] = str(tmp / "runs")
    import check_multiply as cm
    cm.N = n

    def mpy(m, w, words):
        c = m.state["multiply_call"]
        return [("AC", w.ac, c["partial"].v), ("IO", w.io, c["low"].v),
                ("mp2", words["mp2"], c["partial"].v), ("mpy", words["mpy"], c["entry"].v)]
    return cm.check("multiply", "mpy", "multiply_call", 1962, "mpy-vectors.jsonl", mpy)


def verify(g: Graph, n: int = 20000) -> int:
    sigs = signatures()
    check(g, sigs)
    order = schedule(g, sigs)
    for seed in range(50):                   # the file's order is not the program's
        r = random.Random(seed)
        h = Graph(g.name, r.sample(g.places, len(g.places)),
                  dict(r.sample(list(g.transitions.items()), len(g.transitions))), r.sample(g.arcs, len(g.arcs)))
        assert schedule(h, sigs) == order, f"shuffle {seed} changed the order"
    print("derived order (same for 50 shuffles of the file):", ", ".join(order))
    failed = 0
    for shared in (False, True):
        at = Storage(g, sigs, shared)
        if shared and (bad := hazards(g, order, at)):
            print("stored: a word is overwritten before it is read:", *bad, sep="\n  ")
            return 1
        source = emit(g, sigs, order, at)
        what = "stored (places sharing PDP-1 words)" if shared else "written once (every place its own field)"
        print(f"--- {what}\n{source}", end="")
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            splice(tmp, source, work_record=not shared)
            failed |= evaluator(tmp, n)
            if shared:
                runsc.BINDINGS = tmp / "pdp1"
                code = runsc.build(runs.program(tmp / "runs"), tmp / "out")
                said = runsc.build.said.strip().splitlines()
                print(*said[-3:], sep="\n")
                failed |= code
    return failed
