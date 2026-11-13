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

A counter may count up to an end instead of to 0 (`counter slot: word
to 030`): a slot of a collection of 030 entries, its tokens the slots
from it to the last. The passes may read it, to look at their slot, and
the user sees where it stopped: the bundle gives it back, the slot a
guard stopped it at, or the end when no guard did. A guard on the take
alone stops the loop: its other side is the loop's end, where the user
takes over. A `stop` in place of a Processor, whose one arc is a guard
on the counter `== end`, halts the machine where the counter reaches
its end, and halts it again each time it is continued (the original's
`hlt; jmp .-1`): the bundle then gives back only a slot a guard stopped
it at.

  network find_slot
    counter slot: word to 030
  transitions
    take: count_down
    full: stop
  arcs
    objects.routine[slot] -> take when != none
    slot -> take.counter
    take.counter -> slot
    slot -> full when == 030

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
count the PDP-1 back end compiles to nothing (pdp1/README.md). A take
under more than one test (the angle reduction's three ways out) is
lowered to `loop at most <count>:`, each test's other side first and
ending in a break, with no count.

A loop bundle over slots, a dispatch over a collection (CONTEXT.md 340-348),
states its slots in place of the counter's type: `counter later: slot + 1
.. 027`. The counter is the pass's slot, which its transitions pass on
(`collision(later)`), and the take steps it to the next slot; the loop ends
past the last. Its count is fixed by the slots it states, so no user sets
it. Lowered, it is `for later in slot + 1 .. 027`.

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
lowers after the dispatch's chain, under its own `if`. A test whose sides
name every member lowers to a `match` (a `!= m` side after it, under its
own `if`); a test whose only side with work is its else, to the test that
holds where the others fail (`if r != none and r != explosion`).

  network calc(slot)
    assumes: table[slot].routine != none
  arcs
    table[slot].routine -> fly when == torpedo
    table[slot].routine -> burst when == explosion

A test may compare its place with another place of the network, as the
PDP-1's sas compares AC with a word: `tally.first -> show when !=
tally.second`. The test reads both.

Today a `run` passes no values, so the lowering keeps a bundle's inputs and
outputs in the fields of its call Record, `<bundle>_call`, which a Record
file declares with exactly the bundle's inputs and outputs. Running a bundle
copies each input into that Record before `run` and each output out of it
after.

A copy takes a value of any kind: its two ends may hold one Record whole
(`calculated -> give.source`, `give.target -> table`). A place that holds
a Record whole and its entries are one value: a read of an entry sees the
writer of the whole, and a read of the whole the writers of its entries.

A top Network, one nothing runs, names its boundary with presentation
(CONTEXT.md 273-276): `requires: console, score` are the Records the
host writes before it fires, `produces: display, lights` those it reads
after. They lower to the Network's `reads:` and `writes:`.

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
    boundary: dict[str, list[str]] = field(default_factory=dict)   # a top Network's requires: and produces: Records
    assumes: list[tuple[str, str]] = field(default_factory=list)   # `assumes: place != member`: a precondition
    bound: str | None = None                              # a loop bundle's counter that starts at a stated count
    locals: dict[str, str] = field(default_factory=dict)  # a place the network holds itself -> its Record or stream
    wholes: set[str] = field(default_factory=set)         # the Records and streams a place may hold whole
    streams: set[str] = field(default_factory=set)        # of those, the streams
    over: tuple[str, str, str] | None = None              # a loop bundle over slots: (its counter, first, last)
    ends: dict[str, str] = field(default_factory=dict)    # a counter -> the end it counts up to, `to 030`
    halt: str | None = None                               # a stop on the counter's end: the loop halts there

    @property
    def call(self) -> str:
        return f"{self.name}_call"

    @property
    def counter(self) -> str | None:
        """A loop bundle's counter: the input whose tokens its passes consume."""
        return next((n for n, (d, _) in self.ports.items() if d == "counter"), None)

    @property
    def end(self) -> str | None:
        """The end a loop bundle's counter counts up to, when not 0."""
        return self.ends.get(self.counter) if self.counter else None

    def threaded(self, place: str) -> bool:
        """A place the network takes and gives: an inout, or a loop bundle's
        counter, which each pass reads and writes."""
        return bool((n := self.port(place)) and self.ports[n][0] in ("inout", "counter"))

    @property
    def stated(self) -> str | None:
        """A loop bundle's counter no user sets: its slots or its count are stated."""
        return self.over[0] if self.over else self.counter if self.bound else None

    def signature(self) -> Signature:
        s = Signature([], [], bundle=True, counter=None if self.stated else self.counter)
        for n, (d, typ) in self.ports.items():
            if n == self.stated:
                continue                                  # its slots or its count are stated: no user sets it
            if d in ("in", "inout", "counter"):
                s.inputs.append(n)
            if d in ("out", "inout") or n in self.ends:     # a counter with an end is given back
                s.outputs.append(n)
            if d == "inout" or n in self.ends:
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
        elif section is None and (m := re.fullmatch(r"\s+(requires|produces): (\w+(?:, \w+)*)", line)):
            g.boundary[m[1]] = [x.strip() for x in m[2].split(",")]
        elif section is None and line.strip().startswith("requires:"):
            g.requires = line.strip()
        elif section is None and line.strip().startswith("assumes:"):
            m = re.fullmatch(rf"\s+assumes: ({NAME}) != (\w+)", line)
            if not m:
                raise GraphError(f"{where}: a precondition is `assumes: place != member`")
            g.assumes.append((m[1], m[2]))
        elif section is None and (m := re.fullmatch(r"\s+counter (\w+): (.+) \.\. (.+)", line)):
            if g.counter:
                raise GraphError(f"{where}: a loop bundle has one counter, not {g.counter} and {m[1]}")
            g.ports[m[1]] = ("counter", "word")
            g.over = (m[1], m[2].strip(), m[3].strip())
        elif section is None:
            m = re.fullmatch(r"\s+(in|out|inout|counter) (\w+): (\w+)(?: = (-?0?\w+)| to (\w+))?", line)
            if not m or (m[4] or m[5]) and m[1] != "counter":
                raise GraphError(f"{where}: a network's input or output is `in name: type`, a loop bundle's "
                                 f"counter `counter name: type`, `counter name: type = -count` or `counter name: type to end`")
            if m[4]:
                g.bound = m[4]
            if m[5]:
                g.ends[m[2]] = m[5]
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
    ends = [a.place for a in g.arcs] + [p for a in g.arcs if (p := operand(g, a.guard))]
    g.places += list(dict.fromkeys(p for p in ends if (g.port(p) or re.match(r"\w+", p)[0] in g.locals)
                                   and p not in g.places))
    halt_at_end(g)
    return g


def operand(g: Graph, guard: str | None) -> str | None:
    """The place a test compares its own with (`!= tally.second`), if any."""
    if not guard or guard == "else":
        return None
    rest = guard.partition(" ")[2]
    if not re.fullmatch(NAME, rest) or re.fullmatch(r"\d\w*", rest):
        return None
    if "." in rest or rest in g.ports or rest in g.locals or rest in g.places:
        return rest
    return None


def halt_at_end(g: Graph) -> None:
    """A loop bundle that counts up to an end may halt there: a stop whose
    one arc is a guard on the counter `== end` (sr1: `index sr1, (lac mtb
    nob, sr1` then `hlt`). The pass that brings the counter to its end
    halts in place of leaving the loop, so the bundle never gives the end
    back; the stop is the loop's counted exit, no transition of a pass."""
    if not g.end:
        return
    for t, proc in list(g.transitions.items()):
        arcs = [a for a in g.arcs if a.transition == t]
        if proc == STOP and [(a.place, a.guard) for a in arcs] == [(g.counter, f"== {g.end}")]:
            if g.halt:
                raise GraphError(f"{g.where}: {g.name} halts at its end once, not at {g.halt} and {t}")
            g.halt = t
            del g.transitions[t]
            g.arcs = [a for a in g.arcs if a.transition != t]


def written_by(g: Graph) -> dict[str, set[str]]:
    """place -> the transitions that write it."""
    writers: dict[str, set[str]] = {}
    for a in g.arcs:
        if not a.into:
            writers.setdefault(a.place, set()).add(a.transition)
    return writers


def sources(g: Graph, place: str, writers: dict[str, set[str]]) -> set[str]:
    """The transitions whose value a read of place sees: its writers, and,
    for a place the network holds whole (`calculated: objects`), the
    writers of the whole when it reads an entry, and of its entries when it
    reads the whole. A Record held whole (`placed: objects`, not a stream)
    is one value: a read of any part sees the writers of every part."""
    root = re.match(r"\w+", place)[0]
    out = set(writers.get(place, set()))
    if root in g.locals:
        one = g.locals[root] not in g.streams
        for p, ws in writers.items():
            if p != place and re.match(r"\w+", p)[0] == root and (one or root in (p, place)):
                out |= ws
    return out


def guards(g: Graph) -> dict[str, tuple[str, str] | None]:
    """A transition's guard: on its own guard arc, else the guard of the one
    branch that writes its inputs (a token is there only on that branch).
    An inout's in value, or a counter's, comes from the network's user: no
    branch writes it."""
    own = {a.transition: (a.place, a.guard) for a in g.arcs if a.guard}
    out: dict[str, tuple[str, str] | None] = {}
    writers = written_by(g)

    def of(t: str):
        if t not in out:
            out[t] = own.get(t)
            if out[t] is None:
                for a in g.arcs:
                    if a.transition == t and a.into and a.io is not None and not g.threaded(a.place):
                        ws = {of(w) for w in sources(g, a.place, writers)}
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


def complement(g: Graph, place: str, side: str) -> bool:
    """A side `!= m` of an n-way dispatch with a side `== m`: every side but
    that one. A `!= m` with no `== m` beside it is a test of its own, with
    its else."""
    return side.startswith("!= ") and any(a.place == place and a.guard == f"== {side[3:]}" for a in g.arcs)


def exclusive(g: Graph, x: tuple[str, str], y: tuple[str, str]) -> bool:
    """Two sides that never both hold: two sides of one test. A side
    `!= m` of an n-way dispatch is every side but `== m`; on a place with
    no `== m` side it is one side of a two-sided test, its else the other."""
    if x[0] != y[0] or x[1] == y[1]:
        return False
    if complement(g, *x) or complement(g, *y):
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
    sides = {p: sorted(gs, key=lambda k: (complement(g, p, k), k == "else")) for p, gs in tests.items()}

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
    wired |= {p for a in g.arcs if (p := operand(g, a.guard))}           # the other place of a test
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
                if type_of(a.place) != s.types[a.io] and not whole_copy(g, t, p, type_of):
                    fail(f"{t}.{a.io} is {s.types[a.io]}, wired to {a.place}, {type_of(a.place)}", a.where)
        for n in s.inout:
            ends = {a.place for a in g.arcs if a.transition == t and a.io == n}
            threaded = len(ends) == 1 and g.threaded(next(iter(ends)))
            if len(ends) != 2 and not threaded:   # a network inout's in value is read, its out value given
                fail(f"{t}.{n} is inout: it takes one place and gives a fresh one, not {sorted(ends)}")
    chain = chains(g)

    def apart(a, b):
        """Two transitions that never both run: on two sides of one test."""
        return any(exclusive(g, x, y) for x, y in zip(chain[a], chain[b]))
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
        guarded = {a.transition for a in g.arcs if a.place == place and a.guard}
        if guarded == {taker(g)} and len(gs) == 1 and "else" not in gs:
            continue                        # the take's guard stops the loop: its other side is the loop's end
        partition(g, place, gs, type_of(place), enums, fail)
        for x in gs:
            if (other := operand(g, x)) is not None:
                if other not in g.places:
                    fail(f"the test on {place} compares it with {other}, no place of {g.name}")
                if type_of(other) != type_of(place):
                    fail(f"the test on {place} compares a {type_of(place)} with {other}, a {type_of(other)}")
    for place, m in g.assumes:
        if place not in tests or m not in enums.get(type_of(place) or "", []):
            fail(f"assumes: {place} != {m} names no member of a value the network tests")
    streams(g, fail)


COPY = "copy"


def whole_copy(g: Graph, t: str, proc: str, type_of) -> bool:
    """A copy of a whole Record: a copy takes a value of any kind and gives
    it unchanged, so its two ends may hold one Record whole. A whole Record
    lives in its own words, so the copy is no code."""
    ends = {type_of(a.place) for a in g.arcs if a.transition == t and a.io}
    return proc == COPY and len(ends) == 1 and ends <= g.wholes


def partition(g: Graph, place: str, gs: set[str], typ: str | None, enums: dict[str, list[str]], fail) -> None:
    """The guards on one place: exactly one true, always (CONTEXT.md
    351-358). One test and its else; or an n-way dispatch, `== m` for
    distinct members or numbers and else last. On an enum the else may go
    when the `==` sides name every member the network does not assume
    away (`assumes: place != member`)."""
    gs = {x for x in gs if not complement(g, place, x)}       # a `!= m` beside `== m`: no side of its own
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
                if not any(exclusive(g, x, y) for x, y in zip(chain[a], chain[b])):
                    fail(f"the stream value {p} is taken by {a} and {b}: a stream runs in one chain")


COUNT_DOWN = "count_down"    # one token taken: the counter one nearer 0 (`count i`, `isp`)
STOP = "stop"                # the machine halts: a transition in place of a Processor


def taker(g: Graph) -> str | None:
    """The transition of a loop bundle that takes a pass's token."""
    return next((a.transition for a in g.arcs if g.counter and a.place == g.counter and not a.into), None)


def loop_bundle(g: Graph, sigs: dict[str, Signature], fail) -> None:
    """A loop bundle's one cycle runs through its counter: a count_down
    takes the counter and gives it back one nearer its end, and nothing
    else writes it; nothing else reads it either, unless it counts up to
    an end (a slot, which the passes look at). Every other place it takes
    and gives (an inout) holds one value a pass. A place a parent wires to
    a counter is consumed: the loop bundle is its one reader."""
    for t, p in g.transitions.items():
        if (n := sigs[p].counter) is None:
            continue
        fed = next(a.place for a in g.arcs if a.transition == t and a.io == n and a.into)
        if others := sorted({a.transition for a in g.arcs if a.place == fed and a.into} - {t}):
            fail(f"{fed} is {t}'s counter, which its passes consume; {others[0]} reads it too")
    if g.counter is None:
        return
    touch = {(a.transition, a.into) for a in g.arcs if a.place == g.counter}
    t = taker(g)
    if g.end:
        touch -= {(a.transition, True) for a in g.arcs if a.place == g.counter and a.into and a.io
                  and a.transition != t}
    if t is None or touch != {(t, True), (t, False)} or g.transitions[t] != COUNT_DOWN:
        fail(f"the counter {g.counter} runs through one {COUNT_DOWN}, which takes it and gives it back, "
             f"and nothing else" + (" writes it" if g.end else ""))
    if g.end and any(a.into and a.place == g.counter and not a.io for a in g.arcs):
        fail(f"the counter {g.counter} is no guard's: the take alone steps it, and the loop ends at {g.end}")


def depends(g: Graph) -> dict[str, set[str]]:
    """t -> the transitions that write a place t reads or its guard reads.
    An inout of the network is read as its in value and written as its out
    value: its writers come after its readers. A Record the network holds
    whole (`placed: objects`) is one value: a transition that reads any of
    it comes after every transition that writes any of it."""
    guard = guards(g)
    writers = written_by(g)
    out: dict[str, set[str]] = {t: set() for t in g.transitions}
    for a in g.arcs:
        if a.into and not g.threaded(a.place) and a.place in g.locals:   # a whole place: the writes of its entries
            out[a.transition] |= {w for p, ws in writers.items() if p.startswith(a.place + ".") for w in ws}
        if a.into and not g.threaded(a.place):
            out[a.transition] |= sources(g, a.place, writers) - {a.transition}
        elif a.into:
            for w in writers.get(a.place, set()) - {a.transition}:
                out[w].add(a.transition)
    for t in g.transitions:
        if guard[t]:
            for place in [guard[t][0]] + [p for test in chains(g)[t] if (p := operand(g, test[1]))]:
                if not g.threaded(place):         # a test of an inout reads its in value
                    out[t] |= sources(g, place, writers)
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
    readers = {p: {a.transition for a in g.arcs if a.place == p and a.into and not a.guard} for p in held}
    tested = {p: {a.transition for a in g.arcs if a.place == p and a.guard} for p in held}
    for p, (kind, fld, index) in held.items():
        for q, (k2, f2, i2) in held.items():
            if p == q or kind != k2 or fld and f2 and (fld, index) != (f2, i2):
                continue
            if (root := re.match(r"\w+", p)[0]) in g.locals and re.match(r"\w+", q)[0] == root:
                continue                                  # a place of its own and its entries: one value
            made = sources(g, p, writers) | \
                {w for x, ws in writers.items() if x.startswith(p + ".") for w in ws}   # a whole place, its entries'
            before_p = set().union(*(earlier(w) | {w} for w in made))
            for u in writers.get(q, set()) - before_p:
                inside = any(gd[0] == p for gd in chain[u])   # p's test is read before u's side runs
                for r in (readers[p] | (set() if inside else tested[p])) - {u}:
                    if not any(exclusive(g, x, y) for x, y in zip(chain[r], chain[u])):
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
    resumes: dict[str, list[str]] = field(default_factory=dict)   # transition -> the statements laid in its stead
    in_place: set[tuple[str, str]] = field(default_factory=set)   # (source, target) of a copy within one word: no code


def steps(g: Graph, sigs: dict[str, Signature], order: list[str], low: Lowering) -> list:
    """Each transition's statements: (the guards it runs under, lines, fields written)."""
    guard = chains(g)
    out = []

    def copy(typ: str, source: str, target: str) -> list[str]:
        return [f"run {low.copier[typ]}", f"  source: {source}", f"  target: {target}"]

    # A bundle laid out inline takes and gives an inout in its out value's field: the in value is
    # copied there just after the transition that gives it, when that runs under the same tests.
    after: dict[str, list[str]] = {}
    before: dict[str, list[str]] = {}
    for t in order:
        proc = g.transitions[t]
        if t in low.resumes or not (sigs[proc].bundle and proc in low.inline):
            continue
        for n in [n for n in sigs[proc].inputs if n in sigs[proc].inout and sigs[proc].types[n] not in g.wholes]:
            src = next(a.place for a in g.arcs if a.transition == t and a.io == n and a.into)
            dst = next(a.place for a in g.arcs if a.transition == t and a.io == n and not a.into)
            if low.at[src] == low.at[dst]:
                continue
            gives = [w for w in order[:order.index(t)] if guard[w] == guard[t]
                     and any(a.transition == w and a.place == src and not a.into for a in g.arcs)]
            (after.setdefault(gives[-1], []) if gives else before.setdefault(t, [])).extend(
                copy(sigs[proc].types[n], low.at[src], low.at[dst]))

    for k, t in enumerate(order):
        if k and order[k - 1] in after:               # the copies just after the transition before
            out.append((guard[order[k - 1]], after[order[k - 1]], set()))
        if t in low.resumes:
            if low.resumes[t]:
                out.append((guard[t], low.resumes[t], set()))
            continue
        proc, s = g.transitions[t], sigs[g.transitions[t]]
        wire: dict[str, dict[str, str]] = {}
        for a in g.arcs:
            if a.transition == t and a.io:
                wire.setdefault(a.io, {})["in" if a.into else "out"] = low.at[a.place]
        written = {wire[o]["out"] for o in s.outputs}
        lines: list[str] = []
        if s.bundle and proc in low.inline:          # a whole Record is in its own words: no wire
            args = [f"  {n}: {wire[n].get('out', wire[n].get('in'))}" for n in dict.fromkeys(s.inputs + s.outputs)
                    if s.types[n] not in g.wholes]
            out.append((guard[t], before.get(t, []) + [f"run {proc}{g.args.get(t, '')}"] + args, written))
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
    if order and order[-1] in after:
        out.append((guard[order[-1]], after[order[-1]], set()))
    return out


def lower(g: Graph, sigs: dict[str, Signature], order: list[str], low: Lowering) -> str:
    """The graph as one Network of today's RUNS: each transition a wired
    run, each side of a test under its `if` or `else`."""
    take = taker(g)
    fold = None
    nested = bool(take and g.bound and len(chains(g)[take]) > 1)
    if take and g.bound and not nested:
        fold, take = fold_guard(g, take, low), None
        order = [t for t in order if t != taker(g)]
    facts = tested_copies(g, sigs, low)
    tested = {p: low.at[src] for p, (_, src) in facts.items()}
    dropped = {t for t, _ in facts.values()}
    order = [t for t in order if t not in dropped]
    body = steps(g, sigs, [t for t in order if t != take] + ([take] if take and not g.over and not nested else []), low)
    def free(lines):
        """A copy within one word, which the PDP-1 lays out as no code."""
        return len(lines) == 3 and lines[0][4:] in low.copier.values() \
            and (lines[1].split(": ")[1], lines[2].split(": ")[1]) in low.in_place

    for within, place in sorted({(gd[:-1], gd[-1][0]) for gd, _, _ in body if gd}):
        then = [i for i, (gd, _, _) in enumerate(body) if gd[:-1] == within and gd and gd[-1][0] == place
                and gd[-1][1] != "else"]
        other = [i for i, (gd, _, _) in enumerate(body) if gd[:-1] == within and gd and gd[-1][0] == place
                 and gd[-1][1] == "else"]
        written = set().union(*(body[i][2] for i in then))
        if then and other and all(body[i][2] and body[i][2] <= written & (low.before_test | (
                body[i][2] if free(body[i][1]) else set())) for i in other):
            moved = [(within, body[i][1], body[i][2]) for i in other]
            for i in reversed(other):
                del body[i]
            at = then[0]
            if all(free(lines) for _, lines, _ in moved):     # no code: as early as its values allow
                names = {line.split(": ")[1] for _, lines, _ in moved for line in lines[1:]}
                while at and body[at - 1][0] == within and not names & {
                        line.split(": ")[1] for line in body[at - 1][1][1:] if ": " in line}:
                    at -= 1
            body[at:at] = moved
    for i in range(len(body)):          # a copy within one word: just after its value is given, as the PDP-1 has it
        if not free(body[i][1]):
            continue
        source = body[i][1][1].split(": ")[1]
        k = i
        while k and body[k - 1][0] == body[i][0] and not free(body[k - 1][1]) \
                and not any(source == w or source.startswith(w + ".") for w in body[k - 1][2]):
            k -= 1
        body.insert(k, body.pop(i))
    if nested:                          # the bound keeps no count: the take is only where the loop goes on
        body = stop_side_first(g, body + [(chains(g)[take], [], set())])[:-1]
    elif take and not g.over and body[-1][0]:
        body = stop_side_first(g, body)
    head = f"network {g.name}({', '.join(g.params)})" if g.params else f"network {g.name}"
    requires = ([g.requires] if g.requires else []) + [f"requires: {low.at[p]} != {m}" for p, m in g.assumes]
    owns = [n for n in low.owns if n != g.stated and n not in {low.at[p] for p in facts}]
    contract = [f"  {'reads' if k == 'requires' else 'writes'}: {', '.join(rs)}" for k, rs in g.boundary.items()]
    out = [head] + contract + [f"  {r}" for r in requires] + [f"  owns {n}: word" for n in owns]
    ports = {n: (d, typ) for n, (d, typ) in g.ports.items() if typ not in g.wholes and n != g.stated}
    if low.wired:
        out += [f"  {'out' if d == 'out' else 'inout'} {n}: {typ}" for n, (d, typ) in ports.items()]
    matches = dispatches(g)

    def pad(gd, depth):
        return "  " * (depth + 1 + sum(1 for t in gd[:depth] if t[0] in matches and not complement(g, *t)))

    opened: tuple = ()
    for gd, lines, _ in body:
        k = 0
        while k < min(len(opened), len(gd)) and opened[k] == gd[k]:
            k += 1
        for depth in range(k, len(gd)):
            test = gd[depth]
            side = depth == k and depth < len(opened) and opened[depth][0] == test[0] \
                and not complement(g, *test)                       # the next side of one test
            if test[0] in matches and not complement(g, *test):
                if not side:
                    out.append(pad(gd, depth) + f"match {tested.get(test[0], low.at[test[0]])}:")
                    out += [pad(gd, depth) + f"  {m}: unreachable" for m in matches[test[0]]]
                out.append(pad(gd, depth) + f"  {test[1][3:]}:")
                continue
            if test[1] == "else" and not side:          # the test's only side with work is its else
                out.append(pad(gd, depth) + f"if {negation(g, test[0], tested.get(test[0], low.at[test[0]]))}:")
                continue
            if other := operand(g, test[1]):
                test = (test[0], f"{test[1].partition(' ')[0]} {low.at[other]}")
            out.append(pad(gd, depth) + ("else:" if test[1] == "else" else
                                         f"{'elif' if side else 'if'} {tested.get(test[0], low.at[test[0]])} "
                                         f"{test[1]}:"))
        opened = gd
        out += [pad(gd, len(gd)) + line for line in lines]
    head = 1 + len(contract) + len(requires) + len(owns) + (len(ports) if low.wired else 0)
    if len(out) == head:
        raise GraphError(f"{g.where}: {g.name} lowers to no statement")
    if fold:
        c = g.counter
        out[head:] = [f"  for {c} in 1 .. {g.bound.lstrip('-')}:", f"    if {c} == 1 or {fold}:",
                      *("    " + x for x in out[head:])]
    if nested:
        out[head:] = [f"  loop at most {g.bound.lstrip('-')}:", *("  " + x for x in out[head:])]
    elif g.over:                        # the take steps the slot: the walk's own step
        out[head:] = [f"  for {g.over[0]} in {g.over[1]} .. {g.over[2]}:", *("  " + x for x in out[head:])]
    elif take:
        c = low.at[g.counter]
        more, done = (f"!= {g.end}", f"== {g.end}") if g.end else ("< 0", ">= 0")
        out[head:] = [f"  if {c} {more}:", f"    loop at most {LOOP_BOUND:#o}:".replace("0o", "0"),
                      *("    " + x for x in out[head:]), f"      if {c} {done}:",
                      "        stop" if g.halt else "        break"]
    return "\n".join(out) + "\n"


def tested_copies(g: Graph, sigs: dict[str, Signature], low: Lowering) -> dict[str, tuple[str, str]]:
    """A copy whose place only tests read, of a place nothing in the network
    writes (the fact a test nested in a side reads: `restart_work.second_routine`):
    the place -> (the copy, its source). Lowered, each test reads the source
    itself, which holds the same value wherever the test stands, and the copy
    is no statement."""
    writers = written_by(g)
    chain = chains(g)
    out = {}
    for t, proc in g.transitions.items():
        if proc not in low.copier.values() or sigs[proc].bundle:
            continue
        src = next(a.place for a in g.arcs if a.transition == t and a.io == "source")
        dst = next(a.place for a in g.arcs if a.transition == t and a.io == "target")
        reads = [a for a in g.arcs if a.place == dst and a.into]
        root = re.match(r"\w+", src)[0]
        later = {w for p, ws in writers.items() if re.match(r"\w+", p)[0] == root for w in ws}

        def after_test(w):
            """w runs under the test, or on another side of a test the copy is under."""
            return any(gd[0] == dst for gd in chain[w]) or \
                any(exclusive(g, x, y) for x, y in zip(chain[w], chain[t]))
        if reads and all(a.guard for a in reads) and writers.get(dst) == {t} and all(map(after_test, later)):
            out[dst] = (t, src)
    return out


def dispatches(g: Graph) -> dict[str, list[str]]:
    """The n-way tests that name every member of an enum and have no else
    (graph.partition) -> the members they assume away. Each lowers to a
    match, an assumed member's arm unreachable."""
    sides: dict[str, set[str]] = {}
    for a in g.arcs:
        if a.guard and not complement(g, a.place, a.guard):   # a `!= m` side lowers under its own `if`
            sides.setdefault(a.place, set()).add(a.guard)
    return {p: [m for q, m in g.assumes if q == p] for p, gs in sides.items()
            if "else" not in gs and len(gs) > 1 and all(x.startswith("== ") for x in gs)}


def negation(g: Graph, place: str, at: str) -> str:
    """The test that holds where every other side of place's test fails."""
    tests = dict.fromkeys(a.guard for a in g.arcs if a.place == place and a.guard and a.guard != "else"
                          and not complement(g, place, a.guard))
    return " and ".join(f"{at} {NEGATED[t.split(' ', 1)[0]]} {t.split(' ', 1)[1]}" for t in tests)


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
    follows it unguarded, the take last. A take under a test in that side
    is laid out the same way, a test at a time (the angle reduction's three
    ways out). body: the steps, the take's last."""
    gd = body[-1][0]
    if not gd:
        return body
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
    return body[:first] + ends + [((stop,), ["break"], set())] + stop_side_first(g, goes)


def written_once(g: Graph, sigs: dict[str, Signature], copier: dict[str, str]) -> str:
    """runs.load's lowering: every place its own field, a bundle's inputs and
    outputs its call Record's, in the wiring's order. An entry indexed by
    an input or output (`objects.routine[slot]`, slot the counter) is
    indexed by that field."""
    bundles = {p for p in g.transitions.values() if sigs[p].bundle}
    word = {(b, n): f"{b}_call.{n}" for b in bundles for n in sigs[b].inputs + sigs[b].outputs}

    def at(p):
        return re.sub(r"\[(\w+)\]", lambda m: f"[{g.field(m[1])}]" if m[1] in g.ports and m[1] != g.stated else m[0], g.field(p))
    return lower(g, sigs, data_order(g), Lowering({p: at(p) for p in g.places}, word, copier))
