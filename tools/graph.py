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

A loop bundle declares one `counter name: type` line, an input set
before the loop starts (CONTEXT.md 196-206). Its one cycle runs through
the counter: a count_down takes it and gives it back one nearer 0, and
nothing else touches it. Each pass fires every transition once and
takes one token; the loop ends when the counter reaches 0, or after a
pass whose take a guard keeps from firing (a guard stops it). The places
it takes and gives (its inouts) hold one value a pass, and its user sees
their final values. The counter holds minus the passes left, as every
counter in Spacewar does (the PDP-1's `isp`).

  network square_root_passes
    counter passes_left: word
    inout root: word
  transitions
    take: count_down
    pass: square_root_pass
  arcs
    passes_left -> take.counter
    take.counter -> passes_left
    root -> pass.root
    pass.root -> root

A counter may start at a count the bundle states, `counter left: word =
-0140`: the most passes the loop makes, set before it starts, which no
user sets. A guard on its take stops the loop before the count runs out
(an outline's codes end at its 7 code), and the lowering is the guarded
fold `for left in 1 .. 0140: if left == 1 or <the take's guard>:`, whose
count the PDP-1 back end compiles to nothing (pdp1/README.md).

A place may hold a whole Record, a whole field of a collection, or a
stream, and an arc end may name one entry of it. An input or output whose
kind is a Record or a stream is that Record whole (`inout table: objects`,
`table[slot].x`); a whole field of a collection has the kind type[N]
(`star_catalog.words`, word[1652]); and a network may hold such a place
itself, one `name: kind` line under places (`drawn: random`,
`shown_bright: display`). A whole place lives in its Record's own words,
so the places of one Record are ordered: a value is read before the next
takes its words (shared_words). A stream's values run in one chain: each
emitter takes the stream so far and gives it with its points after
(`inout points: display`), so the lowering appends in the chain's order.

A test has two sides, `when <test>` and `when else`, or is an n-way
dispatch: `when == m` for distinct members or numbers, then `when else`.
Exactly one side is true (CONTEXT.md 351-358). On an enum the sides may
name every member in place of the else, less the members a precondition
rules out (`assumes: routine != none`, lowered to `requires:`). Any other
value needs its else. A transition may run on every side of a dispatch
but one, `when != m` where a side is `when == m`: the same partition, not
a second test (an outline's codes: each but the end takes a token). It
lowers after the dispatch's chain, under its own `if`.

  network calc(slot)
    assumes: table[slot].routine != none
  arcs
    table[slot].routine -> fly when == torpedo
    table[slot].routine -> burst when == explosion

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
    counter: str | None = None  # a loop bundle's counter: an input its passes consume


@dataclass
class Graph:
    name: str
    where: str
    ports: dict[str, tuple[str, str]]          # name -> (in, out, inout or counter; type)
    places: list[str]
    transitions: dict[str, str]                # transition -> Processor or bundle
    arcs: list[Arc]
    params: list[str] = field(default_factory=list)       # which slot, as `network torpedo(slot)`
    args: dict[str, str] = field(default_factory=dict)    # transition -> the slot it passes, "(slot)"
    requires: str = ""                                    # `requires: slot < 2`, on the lowered Network
    assumes: list[tuple[str, str]] = field(default_factory=list)   # `assumes: place != member`: a precondition
    bound: str | None = None                              # a loop bundle's counter that starts at a stated count
    locals: dict[str, str] = field(default_factory=dict)  # a place the network holds itself -> its Record or stream
    wholes: set[str] = field(default_factory=set)         # the Records and streams a place may hold whole
    streams: set[str] = field(default_factory=set)        # of those, the streams

    @property
    def call(self) -> str:
        return f"{self.name}_call"

    @property
    def counter(self) -> str | None:
        """A loop bundle's counter: the input whose tokens its passes consume."""
        return next((n for n, (d, _) in self.ports.items() if d == "counter"), None)

    def threaded(self, place: str) -> bool:
        """A place the network takes and gives: an inout, or a loop bundle's
        counter, which each pass reads and writes."""
        return bool((n := self.port(place)) and self.ports[n][0] in ("inout", "counter"))

    def signature(self) -> Signature:
        s = Signature([], [], bundle=True, counter=None if self.bound else self.counter)
        for n, (d, typ) in self.ports.items():
            if d == "counter" and self.bound:
                continue                      # its own: it starts at the stated count, no user sets it
            if d in ("in", "inout", "counter"):
                s.inputs.append(n)
            if d in ("out", "inout"):
                s.outputs.append(n)
            if d == "inout":
                s.inout.add(n)
            s.types[n] = typ
        return s

    def port(self, place: str) -> str | None:
        """The input or output a place is, or is an entry of (`table[slot].x`,
        `seed.number`)."""
        root = re.match(r"\w+", place)[0]
        return root if root in self.ports else None

    def whole(self, place: str) -> str | None:
        """The Record or stream a place holds whole, or holds an entry of:
        an input or output of a Record's or a stream's kind, or a place
        the network holds itself (`shown: display`)."""
        root = re.match(r"\w+", place)[0]
        if root in self.locals:
            return self.locals[root]
        if root in self.ports and (root in self.records):
            return self.ports[root][1]
        return None

    def field(self, place: str) -> str:
        """A place as a Record field: an input or output is its call Record's;
        an entry of a Record input or output is that Record's. A whole
        Record or stream lives in its own words: the place is the Record."""
        if kind := self.whole(place):
            index, fld = re.fullmatch(r"\w+(?:\[(\w+)\])?(?:\.(\w+))?", place).groups()
            return kind if fld is None else f"{kind}.{fld}" + (f"[{index}]" if index else "")
        return place if "." in place else f"{self.call}.{place}"

    @property
    def records(self) -> set[str]:
        """The inputs and outputs that are a whole Record: named by entry, or
        of a Record's or a stream's kind."""
        return {n for n, (_, typ) in self.ports.items()
                if typ in self.wholes or any(a.place != n and self.port(a.place) == n for a in self.arcs)}


NAME = r"\w+(?:\[\w+\])?(?:\.\w+(?:\[\w+\])?)?"


def parse(path: Path) -> Graph:
    g = Graph("", str(path), {}, [], {}, [])
    section = None
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split("#")[0].rstrip()
        where = f"{path}:{n}"
        if not line:
            continue
        if line.startswith("network "):
            m = re.fullmatch(r"network (\w+)(?:\((.*)\))?", line.strip())
            if not m:
                raise GraphError(f"{where}: a network line is `network name` or `network name(slot)`")
            g.name, g.params = m[1], [x.strip() for x in (m[2] or "").split(",") if x.strip()]
        elif not line.startswith(" "):
            section = line.strip()
            if section not in ("places", "transitions", "arcs"):
                raise GraphError(f"{where}: unknown section {section!r}")
        elif section is None and line.strip().startswith("requires:"):
            g.requires = line.strip()
        elif section is None and line.strip().startswith("assumes:"):
            m = re.fullmatch(rf"\s+assumes: ({NAME}) != (\w+)", line)
            if not m:
                raise GraphError(f"{where}: a precondition is `assumes: place != member`")
            g.assumes.append((m[1], m[2]))
        elif section is None:
            m = re.fullmatch(r"\s+(in|out|inout|counter) (\w+): (\w+)(?: = (-?0?\w+))?", line)
            if not m or m[4] and m[1] != "counter":
                raise GraphError(f"{where}: a network's input or output is `in name: type`, "
                                 f"a loop bundle's counter `counter name: type` or `counter name: type = -count`")
            if m[4]:
                g.bound = m[4]
            if m[2] in g.ports:
                raise GraphError(f"{where}: {g.name} names {m[2]} twice")
            if m[1] == "counter" and g.counter:
                raise GraphError(f"{where}: a loop bundle has one counter, not {g.counter} and {m[2]}")
            g.ports[m[2]] = (m[1], m[3])
        elif section == "places":
            if m := re.fullmatch(r"\s+(\w+): (\w+)", line):
                g.locals[m[1]] = m[2]
            g.places.append(line.strip().split(":")[0])
        elif section == "transitions":
            t, _, p = line.partition(":")
            if t.strip() in g.transitions:
                raise GraphError(f"{where}: transition {t.strip()} named twice")
            m = re.fullmatch(r"(\w+)(\(.*\))?", p.strip())
            if not m:
                raise GraphError(f"{where}: a transition is `name: Processor` or `name: Processor(slot)`")
            g.transitions[t.strip()] = m[1]
            if m[2]:
                g.args[t.strip()] = m[2]
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
    g.places += list(dict.fromkeys(a.place for a in g.arcs if (g.port(a.place) or re.match(r"\w+", a.place)[0]
                                                                in g.locals) and a.place not in g.places))
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
                    if a.transition == t and a.into and a.io is not None:
                        ws = {of(w.transition) for w in g.arcs if w.place == a.place and not w.into}
                        if len(ws) == 1 and (w := ws.pop()):
                            out[t] = w
        return out[t]
    for t in g.transitions:
        of(t)
    return out


def enclosing(g: Graph) -> dict[str, tuple[str, str] | None]:
    """Each test's place -> the side its test lies in: the guard of the
    transitions that write the place, when they all have one; else None,
    the network's top."""
    guard = guards(g)
    out: dict[str, tuple[str, str] | None] = {}
    for a in g.arcs:
        if a.guard:
            ws = {guard[w.transition] for w in g.arcs if w.place == a.place and not w.into}
            out[a.place] = ws.pop() if len(ws) == 1 else None
    return out


def chains(g: Graph) -> dict[str, tuple[tuple[str, str], ...]]:
    """t -> the guards it runs under, the outermost first."""
    guard, encl = guards(g), enclosing(g)
    out = {}
    for t in g.transitions:
        c, gd = [], guard[t]
        while gd and gd not in c:
            c.insert(0, gd)
            gd = encl.get(gd[0])
        out[t] = tuple(c)
    return out


def exclusive(x: tuple[str, str], y: tuple[str, str]) -> bool:
    """Two sides that never both hold: two sides of one test. A side
    `!= m` of an n-way dispatch is every side but `== m`."""
    if x[0] != y[0] or x[1] == y[1]:
        return False
    if x[1].startswith("!= ") or y[1].startswith("!= "):
        return {x[1][3:], y[1][3:]} == {x[1][3:]} and {x[1][:2], y[1][:2]} == {"==", "!="}
    return True


def levels(g: Graph):
    """The units of each level: within a side (or None, the top) -> the
    transitions under exactly that side and the tests that lie in it; each
    test's sides, its test's side first and else last; and, for a level,
    which of its units holds a transition."""
    guard, encl, chain = guards(g), enclosing(g), chains(g)
    tests: dict[str, list[str]] = {}
    for a in g.arcs:
        if a.guard:
            tests.setdefault(a.place, [])
            if a.guard not in tests[a.place]:
                tests[a.place].append(a.guard)
    sides = {p: sorted(gs, key=lambda k: (k.startswith("!= "), k == "else")) for p, gs in tests.items()}

    def members(within):
        return [t for t in g.transitions if guard[t] == within] + [p for p in tests if encl[p] == within]

    def holder(t, within):
        c = chain[t]
        if within is not None and within not in c:
            return None
        depth = 0 if within is None else c.index(within) + 1
        return t if len(c) == depth else c[depth][0]
    return members, sides, holder


def check(g: Graph, sigs: dict[str, Signature], fields: dict[str, dict[str, str]],
          counts: dict[str, int | None] | None = None, enums: dict[str, list[str]] | None = None) -> None:
    """Every input and output wired once, to a place of its type; every place
    a Record field or one of the network's own inputs and outputs; each place
    written once, or once on each branch of one test; each test a partition."""
    counts, enums = counts or {}, enums or {}

    def fail(msg: str, where: str = g.where):
        raise GraphError(f"{where}: {g.name}: {msg}")

    def type_of(place: str) -> str | None:
        if place in g.ports:
            return g.ports[place][1]
        if place in g.locals:
            return g.locals[place]
        f = g.field(place) if g.port(place) or g.whole(place) else place
        rec, _, fld = re.sub(r"\[\w+\]", "", f).partition(".")
        typ = fields.get(rec, {}).get(fld)
        if typ and counts.get(rec) is not None and "[" not in f:
            return f"{typ}[{counts[rec]:o}]"            # a whole field of a collection
        return typ

    for p in g.places:
        if type_of(p) is None:
            fail(f"{p} is neither a Record field nor an input or output of {g.name}")
    wired = {a.place for a in g.arcs} | {re.match(r"\w+", a.place)[0] for a in g.arcs}   # a whole place, or an entry
    if stated := sorted(set(g.places) - wired - set(g.ports)):
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
            threaded = len(ends) == 1 and g.threaded(next(iter(ends)))
            if len(ends) != 2 and not threaded:   # a network inout's in value is read, its out value given
                fail(f"{t}.{n} is inout: it takes one place and gives a fresh one, not {sorted(ends)}")
    chain = chains(g)

    def apart(a, b):
        """Two transitions that never both run: on two sides of one test."""
        return any(exclusive(x, y) for x, y in zip(chain[a], chain[b]))
    for place in g.places:
        writers = [a.transition for a in g.arcs if a.place == place and not a.into]
        if g.port(place) and g.ports[g.port(place)][0] == "in" and writers:
            fail(f"{place} is an input of {g.name}; {writers[0]} writes it")

        if any(not apart(a, b) for i, a in enumerate(writers) for b in writers[i + 1:]):
            fail(f"{place} is written by {sorted(writers)}: a place is written once on each path")
    for n, (d, _) in g.ports.items():
        if d not in ("in", "counter") and not any(g.port(a.place) == n and not a.into for a in g.arcs):
            fail(f"nothing gives its output {n}")
    loop_bundle(g, sigs, fail)
    tests: dict[str, set[str]] = {}
    for a in g.arcs:
        if a.guard:
            tests.setdefault(a.place, set()).add(a.guard)
    for place, gs in tests.items():
        partition(g, place, gs, type_of(place), enums, fail)
    for place, m in g.assumes:
        if place not in tests or m not in enums.get(type_of(place) or "", []):
            fail(f"assumes: {place} != {m} names no member of a value the network tests")
    streams(g, fail)


def partition(g: Graph, place: str, gs: set[str], typ: str | None, enums: dict[str, list[str]], fail) -> None:
    """The guards on one place: exactly one true, always (CONTEXT.md
    351-358). One test and its else; or an n-way dispatch, `== m` for
    distinct members or numbers and else last. On an enum the else may go
    when the `==` sides name every member the network does not assume
    away (`assumes: place != member`)."""
    but = {x for x in gs if x.startswith("!= ")}
    if stray := sorted(x for x in but if f"== {x[3:]}" not in gs):
        fail(f"the guard {stray[0]} on {place} names no side `== {stray[0][3:]}`: `!= m` is every side of an "
             f"n-way dispatch but `== m`")
    gs = gs - but
    if len(gs) == 2 and "else" in gs:
        return
    eq = sorted(x[3:] for x in gs if x.startswith("== "))
    if len(eq) + ("else" in gs) != len(gs) or len(eq) < 2:
        fail(f"the guards on {place}, {sorted(gs)}, are neither one test and its else nor an n-way dispatch")
    members = enums.get(typ or "")
    if members and (bad := sorted(set(eq) - set(members))):
        fail(f"the guards on {place} name {bad[0]}, no member of {typ}")
    if "else" in gs:
        return
    assumed = {m for p, m in g.assumes if p == place}
    if not members:
        fail(f"the guards on {place} leave its other values with no side: an open-typed value takes `when else`")
    if left := sorted(set(members) - set(eq) - assumed):
        fail(f"the guards on {place} leave {left[0]} with no side: add `when else`, or `assumes: {place} != {left[0]}`")


def streams(g: Graph, fail) -> None:
    """A stream's values run in one chain: each is taken by one transition on
    each path, which gives the next (an emitter takes the stream so far and
    gives it with its points after), so the lowering appends to the stream
    in the chain's order."""
    chain = chains(g)
    for p in g.places:
        if g.whole(p) not in g.streams:
            continue
        takers = [a.transition for a in g.arcs if a.place == p and a.into and a.io]
        for i, a in enumerate(takers):
            for b in takers[i + 1:]:
                if not any(exclusive(x, y) for x, y in zip(chain[a], chain[b])):
                    fail(f"the stream value {p} is taken by {a} and {b}: a stream runs in one chain")


COUNT_DOWN = "count_down"    # one token taken: the counter one nearer 0 (`count i`, `isp`)


def taker(g: Graph) -> str | None:
    """The transition of a loop bundle that takes a pass's token."""
    return next((a.transition for a in g.arcs if g.counter and a.place == g.counter and not a.into), None)


def loop_bundle(g: Graph, sigs: dict[str, Signature], fail) -> None:
    """A loop bundle's one cycle runs through its counter: a count_down
    takes the counter and gives it back one nearer 0, and nothing else
    reads or writes it. Every other place it takes and gives (an inout)
    holds one value a pass. A place a parent wires to a counter is
    consumed: the loop bundle is its one reader."""
    for t, p in g.transitions.items():
        if (n := sigs[p].counter) is None:
            continue
        fed = next(a.place for a in g.arcs if a.transition == t and a.io == n)
        if others := sorted({a.transition for a in g.arcs if a.place == fed and a.into} - {t}):
            fail(f"{fed} is {t}'s counter, which its passes consume; {others[0]} reads it too")
    if g.counter is None:
        return
    touch = {(a.transition, a.into) for a in g.arcs if a.place == g.counter}
    t = taker(g)
    if t is None or touch != {(t, True), (t, False)} or g.transitions[t] != COUNT_DOWN:
        fail(f"the counter {g.counter} runs through one {COUNT_DOWN}, which takes it and gives it back, "
             f"and nothing else")


def depends(g: Graph) -> dict[str, set[str]]:
    """t -> the transitions that write a place t reads or its guard reads.
    An inout of the network is read as its in value and written as its out
    value: its writers come after its readers."""
    guard = guards(g)
    writers: dict[str, set[str]] = {}
    for a in g.arcs:
        if not a.into:
            writers.setdefault(a.place, set()).add(a.transition)
    out: dict[str, set[str]] = {t: set() for t in g.transitions}
    for a in g.arcs:
        if a.into and not g.threaded(a.place) and a.place in g.locals:   # a whole place: the writes of its entries
            out[a.transition] |= {w for p, ws in writers.items() if p.startswith(a.place + ".") for w in ws}
        if a.into and not g.threaded(a.place):
            out[a.transition] |= writers.get(a.place, set())
        elif a.into:
            for w in writers.get(a.place, set()) - {a.transition}:
                out[w].add(a.transition)
    for t in g.transitions:
        if guard[t]:
            out[t] |= writers.get(guard[t][0], set())
    return shared_words(g, out, writers)


def shared_words(g: Graph, out: dict[str, set[str]], writers: dict[str, set[str]]) -> dict[str, set[str]]:
    """Places that hold a Record whole, or an entry of it, live in its words:
    `drawn: random` and the input seed are one word, random.number. A value
    in those words is read before the next value takes them: each reader
    of a place goes before the writer of another place in the same words,
    unless that writer comes first by the wiring or never runs on the same
    path."""
    def words(p):
        kind = g.whole(p)
        if kind is None or kind in g.streams:
            return None
        index, fld = re.fullmatch(r"\w+(?:\[(\w+)\])?(?:\.(\w+))?", p).groups()
        return kind, fld, index

    held = {p: w for p in g.places if (w := words(p))}
    if not any(re.match(r"\w+", p)[0] in g.locals for p in held):
        return out
    chain = chains(g)

    def earlier(t):
        seen, todo = set(), [t]
        while todo:
            for d in out[todo.pop()] - seen:
                seen.add(d)
                todo.append(d)
        return seen
    readers = {p: {a.transition for a in g.arcs if a.place == p and a.into} for p in held}
    for p, (kind, fld, index) in held.items():
        for q, (k2, f2, i2) in held.items():
            if p == q or kind != k2 or fld and f2 and (fld, index) != (f2, i2):
                continue
            if (root := re.match(r"\w+", p)[0]) in g.locals and re.match(r"\w+", q)[0] == root:
                continue                                  # a place of its own and its entries: one value
            made = {w for x, ws in writers.items() if x == p or x.startswith(p + ".") for w in ws}  # a whole place, its entries'
            before_p = set().union(*(earlier(w) | {w} for w in made))
            for u in writers.get(q, set()) - before_p:
                for r in readers[p] - {u}:
                    if not any(exclusive(x, y) for x, y in zip(chain[r], chain[u])):
                        out[u].add(r)
    return out


def before_in(g: Graph, within, members, holder) -> dict[str, set[str]]:
    """The units of a level -> the units of that level they come after."""
    before: dict[str, set[str]] = {u: set() for u in members}
    for t, ds in depends(g).items():
        if (ut := holder(t, within)) is None:
            continue
        for d in ds:
            if (ud := holder(d, within)) is not None and ud != ut:
                before[ut].add(ud)
    return before


def ordered(g: Graph, choose) -> list[str]:
    """An order the wiring allows: each transition after the transitions it
    depends on, each side of a test one block, a test that lies in a side
    inside that side's block. Among the units that may go next at a level,
    choose(ready, done) picks one."""
    members, sides, holder = levels(g)
    done: list[str] = []

    def level(within):
        ms = members(within)
        before = before_in(g, within, ms, holder)
        placed: set[str] = set()
        while len(placed) < len(ms):
            ready = sorted(u for u in ms if u not in placed and before[u] <= placed)
            if not ready:
                raise GraphError(f"{g.where}: {g.name}: the wiring has a cycle")
            u = choose(ready, done)
            placed.add(u)
            if u in sides:
                for side in sides[u]:
                    level((u, side))
            else:
                done.append(u)
    level(None)
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
    inline: set[str] = field(default_factory=set)   # bundles whose run wires each input and output to its word
    wired: bool = False        # this Network's inputs and outputs are wired by the run that runs it


def steps(g: Graph, sigs: dict[str, Signature], order: list[str], low: Lowering) -> list:
    """Each transition's statements: (the guards it runs under, lines, fields written)."""
    guard = chains(g)
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
        if s.bundle and proc in low.inline:
            args = [f"  {n}: {wire[n].get('out', wire[n].get('in'))}" for n in dict.fromkeys(s.inputs + s.outputs)
                    if s.types[n] not in g.wholes]       # a whole Record lives in its own words
            out.append((guard[t], [f"run {proc}"] + args, written))
            continue
        if s.bundle:
            for n, ends in wire.items():
                if s.types[n] in g.wholes and set(ends.values()) != {s.types[n]}:
                    raise GraphError(f"{g.where}: {t}.{n} is {proc}'s {s.types[n]}, whole: it is wired to a place "
                                     f"in the words of {s.types[n]}, not {sorted(set(ends.values()))}")
            for n in [n for n in s.inputs if s.types[n] not in g.wholes]:
                if wire[n]["in"] != (w := low.word[proc, n]):
                    lines += copy(s.types[n], wire[n]["in"], w)
            lines.append(f"run {proc}{g.args.get(t, '')}")
            for n in [n for n in s.outputs if s.types[n] not in g.wholes]:
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
        out.append((guard[t], lines + [f"run {proc}{g.args.get(t, '')}"] + args, written))
    return out


def lower(g: Graph, sigs: dict[str, Signature], order: list[str], low: Lowering) -> str:
    """The graph as one Network of today's RUNS: each transition a wired
    run, each side of a test under its `if` or `else`."""
    take = taker(g)
    fold = None
    if take and g.bound:
        fold, take = fold_guard(g, take, low), None
        order = [t for t in order if t != taker(g)]
    body = steps(g, sigs, [t for t in order if t != take] + ([take] if take else []), low)
    for place in sorted({gd[0][0] for gd, _, _ in body if len(gd) == 1}):
        then = [i for i, (gd, _, _) in enumerate(body) if gd and gd[-1][0] == place and gd[-1][1] != "else"]
        other = [i for i, (gd, _, _) in enumerate(body) if gd and gd[-1][0] == place and gd[-1][1] == "else"]
        written = set().union(*(body[i][2] for i in then))
        if then and other and all(body[i][2] <= written & low.before_test for i in other):
            moved = [((), body[i][1], body[i][2]) for i in other]
            for i in reversed(other):
                del body[i]
            body[then[0]:then[0]] = moved
    if take and body[-1][0]:
        body = stop_side_first(g, body)
    head = f"network {g.name}({', '.join(g.params)})" if g.params else f"network {g.name}"
    requires = ([g.requires] if g.requires else []) + [f"requires: {low.at[p]} != {m}" for p, m in g.assumes]
    out = [head] + [f"  {r}" for r in requires] + [f"  owns {n}: word" for n in low.owns]
    wired = [(n, d, typ) for n, (d, typ) in g.ports.items() if typ not in g.wholes and not (d == "counter" and g.bound)]
    if low.wired:
        out += [f"  {'out' if d == 'out' else 'inout'} {n}: {typ}" for n, d, typ in wired]
    opened: tuple = ()
    for gd, lines, _ in body:
        k = 0
        while k < min(len(opened), len(gd)) and opened[k] == gd[k]:
            k += 1
        for depth in range(k, len(gd)):
            test = gd[depth]
            side = depth == k and depth < len(opened) and opened[depth][0] == test[0] \
                and not test[1].startswith("!= ")                  # the next side of one test
            out.append("  " * (depth + 1) + ("else:" if test[1] == "else" else
                                             f"{'elif' if side else 'if'} {low.at[test[0]]} {test[1]}:"))
        opened = gd
        out += ["  " * (len(gd) + 1) + line for line in lines]
    head = 1 + len(requires) + len(low.owns) + (len(wired) if low.wired else 0)
    if len(out) == head:
        raise GraphError(f"{g.where}: {g.name} lowers to no statement")
    if fold:
        c = g.counter
        out[head:] = [f"  for {c} in 1 .. {g.bound.lstrip('-')}:", f"    if {c} == 1 or {fold}:",
                      *("    " + x for x in out[head:])]
    if take:
        c = low.at[g.counter]
        out[head:] = [f"  if {c} < 0:", f"    loop at most {LOOP_BOUND:#o}:".replace("0o", "0"),
                      *("    " + x for x in out[head:]), f"      if {c} >= 0:", "        break"]
    return "\n".join(out) + "\n"


LOOP_BOUND = 0o400001     # more passes than an 18-bit counter below 0 holds tokens
NEGATED = {"<": ">=", ">=": "<", ">": "<=", "<=": ">", "==": "!=", "!=": "=="}


def fold_guard(g: Graph, take: str, low: Lowering) -> str:
    """A loop bundle whose counter starts at a stated count is the guarded
    fold `for c in 1 .. count: if c == 1 or <test>:`, where the test is the
    take's guard: the pass that ends the loop takes no token, and the
    passes after it do nothing. The count is the bound the loop keeps
    (pdp1/README.md, a guarded fold)."""
    chain = chains(g)[take]
    if len(chain) != 1:
        raise GraphError(f"{g.where}: {g.name}: a counter that starts at a stated count needs a guard on its "
                         f"take, which stops the loop")
    place, side = chain[0]
    if side == "else":
        test = next(a.guard for a in g.arcs if a.place == place and a.guard and a.guard != "else")
        op, _, rest = test.partition(" ")
        side = f"{NEGATED[op]} {rest}"
    return f"{low.at[place]} {side}"


def stop_side_first(g: Graph, body: list) -> list:
    """A loop bundle whose take runs on one side of a test: a pass on the
    other side takes no token, and the loop ends after it. That side is
    laid out first, under its own test, ending in a break; the take's side
    follows it unguarded, the take last. body: the steps, the take's last."""
    gd = body[-1][0]
    if len(gd) != 1:
        raise GraphError(f"{g.where}: {g.name}: the take runs on one side of one test, not under {len(gd)}")
    place, side = gd[0]
    test = next(a.guard for a in g.arcs if a.place == place and a.guard and a.guard != "else")
    op, _, rest = test.partition(" ")
    stop = (place, test if side == "else" else f"{NEGATED[op]} {rest}")
    first = next(i for i, (d, _, _) in enumerate(body) if d)
    if any(not d for d, _, _ in body[first:]):
        raise GraphError(f"{g.where}: {g.name}: a pass that takes no token ends the loop, "
                         f"so every transition off the test's sides comes before it")
    ends = [((stop,) + d[1:], lines, w) for d, lines, w in body[first:] if d[0] != gd[0]]
    goes = [(d[1:], lines, w) for d, lines, w in body[first:] if d[0] == gd[0]]
    return body[:first] + ends + [((stop,), ["break"], set())] + goes


def written_once(g: Graph, sigs: dict[str, Signature], copier: dict[str, str]) -> str:
    """runs.load's lowering: every place its own field, a bundle's inputs and
    outputs its call Record's, in the wiring's order."""
    bundles = {p for p in g.transitions.values() if sigs[p].bundle}
    word = {(b, n): f"{b}_call.{n}" for b in bundles for n in sigs[b].inputs + sigs[b].outputs}
    return lower(g, sigs, data_order(g), Lowering({p: g.field(p) for p in g.places}, word, copier))
