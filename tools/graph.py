"""The arcs format: a network file read as a graph, checked, and lowered to
the RUNS that today's Evaluator and runsc run.

A network file states places, transitions and arcs, one arc a line, and no
order (docs/prototypes/graph-format/README.md). A bundle declares its
inputs and outputs with `in`, `out` and `inout` lines, as a Processor file
does; inside it, an arc end that is one name is one of them. A parent uses
a bundle with the same transition line as a Processor.

  network multiply
    in entry: word
    out partial: word
  places
    multiply_work.signs
  transitions
    sign_of_product: exclusive_or
  arcs
    factor -> sign_of_product.a
    sign_of_product.result -> multiply_work.signs
    multiply_work.signs -> reload_high when < 0

Today a `run` passes no values, so the lowering keeps a bundle's inputs and
outputs in the fields of its call Record, `<bundle>_call`, which a Record
file declares with exactly the bundle's inputs and outputs. Running a bundle
copies each input into that Record before `run` and each output out of it
after.

`lower` writes one Network for a graph, in an order and with each place at
a word that the caller chooses. runs.load lowers every graph with
`written_once`: every place its own field, in an order derived from the
wiring alone. The PDP-1 back end (runsc) lowers it with its own order and
its own words."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


class GraphError(Exception):
    pass


@dataclass(frozen=True)
class Arc:
    place: str                 # record.field, or one of the network's own inputs and outputs
    transition: str
    io: str | None             # the Processor's input or output; None on a guard arc
    into: bool                 # place -> transition
    guard: str | None = None   # "< 0", or "else"; only on a guard arc
    where: str = ""


@dataclass
class Signature:
    inputs: list[str]          # in and inout
    outputs: list[str]         # out and inout
    inout: set[str] = field(default_factory=set)
    types: dict[str, str] = field(default_factory=dict)
    bundle: bool = False       # a network file's, which a run of its own Network runs


@dataclass
class Graph:
    name: str
    where: str
    ports: dict[str, tuple[str, str]]          # name -> (in, out or inout; type)
    places: list[str]
    transitions: dict[str, str]                # transition -> Processor or bundle
    arcs: list[Arc]

    @property
    def call(self) -> str:
        return f"{self.name}_call"

    def signature(self) -> Signature:
        s = Signature([], [], bundle=True)
        for n, (d, typ) in self.ports.items():
            if d in ("in", "inout"):
                s.inputs.append(n)
            if d in ("out", "inout"):
                s.outputs.append(n)
            if d == "inout":
                s.inout.add(n)
            s.types[n] = typ
        return s

    def field(self, place: str) -> str:
        """A place as a Record field: an input or output is its call Record's."""
        return place if "." in place else f"{self.call}.{place}"


NAME = r"\w+(?:\[\w+\])?(?:\.\w+)?"


def parse(path: Path) -> Graph:
    g = Graph("", str(path), {}, [], {}, [])
    section = None
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split("#")[0].rstrip()
        where = f"{path}:{n}"
        if not line:
            continue
        if line.startswith("network "):
            g.name = line.split()[1]
        elif not line.startswith(" "):
            section = line.strip()
            if section not in ("places", "transitions", "arcs"):
                raise GraphError(f"{where}: unknown section {section!r}")
        elif section is None:
            m = re.fullmatch(r"\s+(in|out|inout) (\w+): (\w+)", line)
            if not m:
                raise GraphError(f"{where}: a network's input or output is `in name: type`")
            if m[2] in g.ports:
                raise GraphError(f"{where}: {g.name} names {m[2]} twice")
            g.ports[m[2]] = (m[1], m[3])
        elif section == "places":
            g.places.append(line.strip())
        elif section == "transitions":
            t, _, p = line.partition(":")
            if t.strip() in g.transitions:
                raise GraphError(f"{where}: transition {t.strip()} named twice")
            g.transitions[t.strip()] = p.strip()
        elif m := re.fullmatch(rf"\s+({NAME}) -> (\w+) when (.+)", line):
            g.arcs.append(Arc(m[1], m[2], None, True, m[3].strip(), where))
        elif m := re.fullmatch(rf"\s+({NAME}) -> ({NAME})", line):
            a, b = m.groups()
            if a.split(".")[0] in g.transitions:
                t, _, io = a.partition(".")
                g.arcs.append(Arc(b, t, io, False, None, where))
            elif b.split(".")[0] in g.transitions:
                t, _, io = b.partition(".")
                g.arcs.append(Arc(a, t, io, True, None, where))
            else:
                raise GraphError(f"{where}: neither end of the arc is a transition")
        else:
            raise GraphError(f"{where}: {line.strip()!r} is not an arc")
    if not g.name:
        raise GraphError(f"{path}: no `network` line")
    if clash := sorted(set(g.transitions) & {p.split(".")[0] for p in g.places}):
        raise GraphError(f"{path}: {clash[0]} names a transition and a Record")
    g.places += [n for n in g.ports if n not in g.places]
    return g


def guards(g: Graph) -> dict[str, tuple[str, str] | None]:
    """A transition's guard: on its own guard arc, else the guard of the one
    branch that writes its inputs (a token is there only on that branch)."""
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


def check(g: Graph, sigs: dict[str, Signature], fields: dict[str, dict[str, str]]) -> None:
    """Every input and output wired once, to a place of its type; every place
    a Record field or one of the network's own inputs and outputs; each place
    written once, or once on each branch of one test; each test with its else."""
    def fail(msg: str, where: str = g.where):
        raise GraphError(f"{where}: {g.name}: {msg}")

    def type_of(place: str) -> str | None:
        if place in g.ports:
            return g.ports[place][1]
        rec, _, fld = re.sub(r"\[\w+\]", "", place).partition(".")
        return fields.get(rec, {}).get(fld)

    for p in g.places:
        if type_of(p) is None:
            fail(f"{p} is neither a Record field nor an input or output of {g.name}")
    if stated := sorted(set(g.places) - {a.place for a in g.arcs} - set(g.ports)):
        fail(f"the place {stated[0]} is wired to nothing")
    for a in g.arcs:
        if a.place not in g.places:
            fail(f"{a.place} is not a place of {g.name}", a.where)
        if a.transition not in g.transitions:
            fail(f"no transition {a.transition}", a.where)
    for t, p in g.transitions.items():
        if p not in sigs:
            fail(f"{t}: no Processor or bundle {p}")
        s = sigs[p]
        for into, want in ((True, s.inputs), (False, s.outputs)):
            got = [a for a in g.arcs if a.transition == t and a.into == into and a.io]
            names = sorted(a.io for a in got)
            if names != sorted(want):
                fail(f"{t}: {'inputs' if into else 'outputs'} wired {names}, {p} has {sorted(want)}")
            for a in got:
                if type_of(a.place) != s.types[a.io]:
                    fail(f"{t}.{a.io} is {s.types[a.io]}, wired to {a.place}, {type_of(a.place)}", a.where)
        for n in s.inout:
            ends = {a.place for a in g.arcs if a.transition == t and a.io == n}
            if len(ends) != 2:
                fail(f"{t}.{n} is inout: it takes one place and gives a fresh one, not {sorted(ends)}")
    guard = guards(g)
    for place in g.places:
        writers = [a.transition for a in g.arcs if a.place == place and not a.into]
        if place in g.ports and g.ports[place][0] == "in" and writers:
            fail(f"{place} is an input of {g.name}; {writers[0]} writes it")
        branches = [guard[w] for w in writers]
        if len(branches) != len(set(branches)) or len(writers) > 1 and not all(branches):
            fail(f"{place} is written by {sorted(writers)}: a place is written once, or once a branch")
        if len(writers) > 1 and len({b[0] for b in branches}) != 1:
            fail(f"{place} is written on branches of different tests")
    for n, (d, _) in g.ports.items():
        if d != "in" and not any(a.place == n and not a.into for a in g.arcs):
            fail(f"nothing gives its output {n}")
    tests: dict[str, set[str]] = {}
    for a in g.arcs:
        if a.guard:
            tests.setdefault(a.place, set()).add(a.guard)
    for place, gs in tests.items():
        if "else" not in gs or len(gs) != 2:
            fail(f"the guards on {place}, {sorted(gs)}, are not one test and its else")


def depends(g: Graph) -> dict[str, set[str]]:
    """t -> the transitions that write a place t reads or its guard reads."""
    guard = guards(g)
    writers: dict[str, set[str]] = {}
    for a in g.arcs:
        if not a.into:
            writers.setdefault(a.place, set()).add(a.transition)
    out: dict[str, set[str]] = {t: set() for t in g.transitions}
    for a in g.arcs:
        if a.into:
            out[a.transition] |= writers.get(a.place, set())
    for t in g.transitions:
        if guard[t]:
            out[t] |= writers.get(guard[t][0], set())
    return out


def units(g: Graph) -> tuple[list[str], dict[str, list[list[str]]]]:
    """The unguarded transitions, and each test's branches: test place -> one
    list of transitions a side, the test's side first and else last."""
    guard = guards(g)
    plain = [t for t in g.transitions if guard[t] is None]
    tests: dict[str, dict[str, list[str]]] = {}
    for t in g.transitions:
        if guard[t]:
            tests.setdefault(guard[t][0], {}).setdefault(guard[t][1], []).append(t)
    return plain, {p: [sides[k] for k in sorted(sides, key=lambda k: k == "else")] for p, sides in tests.items()}


def ordered(g: Graph, choose) -> list[str]:
    """An order the wiring allows: each transition after the transitions it
    depends on, each side of a test one block. Among the units that may go
    next, choose(ready, done) picks one; inside a side, the same."""
    plain, tests = units(g)
    dep = depends(g)
    member = {t: p for p, sides in tests.items() for side in sides for t in side}
    unit_of = lambda t: member.get(t, t)  # noqa: E731
    before = {u: set() for u in plain + list(tests)}
    for t, ds in dep.items():
        for d in ds:
            if unit_of(d) != unit_of(t):
                before[unit_of(t)].add(unit_of(d))
    done: list[str] = []
    placed: set[str] = set()
    while len(placed) < len(before):
        ready = sorted(u for u in before if u not in placed and before[u] <= placed)
        if not ready:
            raise GraphError(f"{g.where}: {g.name}: the wiring has a cycle")
        u = choose(ready, done)
        placed.add(u)
        if u not in tests:
            done.append(u)
            continue
        for side in tests[u]:
            left = list(side)
            while left:
                inner = sorted(t for t in left if not dep[t] & set(left))
                t = choose(inner, done)
                left.remove(t)
                done.append(t)
    return done


def data_order(g: Graph) -> list[str]:
    """The order runs.load lowers in: the wiring's, with names breaking ties.
    Any order the wiring allows computes the same values."""
    return ordered(g, lambda ready, done: ready[0])


@dataclass
class Lowering:
    """What a lowering decides: where each place lives, and which Processor
    copies a value of each type (a bundle's inputs and outputs, an inout's
    fresh place)."""
    at: dict[str, str]                         # place -> the field it lives in
    word: dict[tuple[str, str], str]           # (bundle, input or output) -> the field it lives in
    copier: dict[str, str]                     # type -> the Processor that copies it
    owns: list[str] = field(default_factory=list)   # the Network's own scratch (register values on the PDP-1)
    before_test: set[str] = field(default_factory=set)  # fields an else may set before its test instead


def steps(g: Graph, sigs: dict[str, Signature], order: list[str], low: Lowering) -> list:
    """Each transition's statements: (guard, lines, fields written)."""
    guard = guards(g)
    out = []

    def copy(typ: str, source: str, target: str) -> list[str]:
        return [f"run {low.copier[typ]}", f"  source: {source}", f"  target: {target}"]

    for t in order:
        proc, s = g.transitions[t], sigs[g.transitions[t]]
        wire: dict[str, dict[str, str]] = {}
        for a in g.arcs:
            if a.transition == t and a.io:
                wire.setdefault(a.io, {})["in" if a.into else "out"] = low.at[a.place]
        written = {wire[o]["out"] for o in s.outputs}
        lines: list[str] = []
        if s.bundle:
            for n in s.inputs:
                if wire[n]["in"] != (w := low.word[proc, n]):
                    lines += copy(s.types[n], wire[n]["in"], w)
            lines.append(f"run {proc}")
            for n in s.outputs:
                if wire[n]["out"] != (w := low.word[proc, n]):
                    lines += copy(s.types[n], w, wire[n]["out"])
            out.append((guard[t], lines, written))
            continue
        if proc in low.copier.values() and wire["source"]["in"] == wire["target"]["out"]:
            continue                                      # the value is already there
        args = []
        for n in s.inputs + [o for o in s.outputs if o not in s.inout]:
            w = wire[n]
            if n in s.inout and w["in"] != w["out"]:
                lines += copy(s.types[n], w["in"], w["out"])
            args.append(f"  {n}: {w.get('out', w.get('in'))}")
        out.append((guard[t], lines + [f"run {proc}"] + args, written))
    return out


def lower(g: Graph, sigs: dict[str, Signature], order: list[str], low: Lowering) -> str:
    """The graph as one Network of today's RUNS: each transition a wired
    run, each side of a test under its `if` or `else`."""
    body = steps(g, sigs, order, low)
    for place in sorted({gd[0] for gd, _, _ in body if gd}):
        then = [i for i, (gd, _, _) in enumerate(body) if gd and gd[0] == place and gd[1] != "else"]
        other = [i for i, (gd, _, _) in enumerate(body) if gd and gd[0] == place and gd[1] == "else"]
        written = set().union(*(body[i][2] for i in then))
        if then and other and all(body[i][2] <= written & low.before_test for i in other):
            moved = [(None, body[i][1], body[i][2]) for i in other]
            for i in reversed(other):
                del body[i]
            body[then[0]:then[0]] = moved
    out = [f"network {g.name}"] + [f"  owns {n}: word" for n in low.owns]
    opened = None
    for gd, lines, _ in body:
        if gd != opened and gd is not None:
            out.append("  else:" if gd[1] == "else" else f"  if {low.at[gd[0]]} {gd[1]}:")
        opened = gd
        pad = "    " if gd else "  "
        out += [pad + line for line in lines]
    if len(out) == 1 + len(low.owns):
        raise GraphError(f"{g.where}: {g.name} lowers to no statement")
    return "\n".join(out) + "\n"


def written_once(g: Graph, sigs: dict[str, Signature], copier: dict[str, str]) -> str:
    """runs.load's lowering: every place its own field, a bundle's inputs and
    outputs its call Record's, in the wiring's order."""
    bundles = {p for p in g.transitions.values() if sigs[p].bundle}
    word = {(b, n): f"{b}_call.{n}" for b in bundles for n in sigs[b].inputs + sigs[b].outputs}
    return lower(g, sigs, data_order(g), Lowering({p: g.field(p) for p in g.places}, word, copier))
