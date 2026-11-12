"""The object walk as bundles in the arc-list format (#57).

Each bundle is a network file here. A transition names a Processor of runs/
with Ports, a bundle here, `copy`, or a routine of runs/ that still names its
Records (a legacy routine, run with its slot). Two line forms are new against
two-level/:

  t: step(slot) for slot in 0 .. 026     a fold: the step bundle runs once a
                                         slot, and each of its inouts threads:
                                         one step's out value is the next's in
  table[slot].x                          an entry of a collection value

and an arc with no input or output on a legacy routine (`table -> first`,
`first -> table`) states which values it reads and gives in their words.

Every value is written once. Inside a bundle, an inout's name read is its in
value and written is its out value; an entry of the out value that nothing
writes is the in value's. The loader checks the wiring, derives each bundle's
order, checks that values sharing a PDP-1 word never overlap (a value is dead
before the next takes its word), and generates today's RUNS source:
object_walk, calc and torpedo.

  uv run -q python docs/prototypes/graph-format/object-walk/load.py [--write]
      [--dir DIR] [--into RUNS]

Without --write it compares the generated source with runs/ and compiles
runs/; with --write it replaces those networks in runs/ first. --dir takes
network files from DIR in place of the ones here of the same name; --into
writes into RUNS (a copy of runs/) and compiles it."""
from __future__ import annotations

import itertools
import random
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import runs, runsc  # noqa: E402

END = r"[\w\[\]\.]+"


@dataclass(frozen=True)
class Arc:
    place: str          # name, name[i].field, or record.field
    transition: str
    io: str | None      # the input or output; None on a guard or legacy arc
    into: bool
    guard: str | None = None


@dataclass
class Use:
    routine: str
    args: list[str]
    fold: tuple[str, str] | None = None     # (variable, range)
    comment: str = ""


@dataclass
class Bundle:
    name: str
    params: list[str]
    ports: list[tuple[str, str, str]]       # (direction, name, kind)
    places: dict[str, str]                  # name -> kind
    uses: dict[str, Use]
    arcs: list[Arc]
    comment: str = ""

    @property
    def boundary(self) -> dict[str, str]:
        return {n: k for _, n, k in self.ports}


@dataclass
class Sig:
    ports: list[tuple[str, str]]            # (direction, name), declared order
    kind: str                               # port, bundle, copy, legacy

    @property
    def inputs(self): return [n for d, n in self.ports if d in ("in", "inout")]

    @property
    def outputs(self): return [n for d, n in self.ports if d in ("out", "inout")]

    @property
    def inout(self): return {n for d, n in self.ports if d == "inout"}


def parse(path: Path) -> Bundle:
    b, section = None, None
    for raw in path.read_text().splitlines():
        line, _, note = raw.partition("#")
        line, note = line.rstrip(), note.strip()
        if not line:
            continue
        if m := re.fullmatch(r"network (\w+)(?:\((.*)\))?", line):
            b = Bundle(m[1], [p.strip() for p in (m[2] or "").split(",") if p.strip()], [], {}, {}, [], note)
        elif not line.startswith(" "):
            section = line
        elif section is None and (m := re.fullmatch(r"\s+(in|out|inout) (\w+): (\w+)", line)):
            b.ports.append(m.groups())
        elif section == "places":
            n, k = (s.strip() for s in line.split(":"))
            b.places[n] = k
        elif section == "transitions":
            m = re.fullmatch(r"\s+(\w+): (\w+)(?:\(([^)]*)\))?(?: for (\w+) in (.+))?", line)
            args = [a.strip() for a in (m[3] or "").split(",") if a.strip()]
            b.uses[m[1]] = Use(m[2], args, (m[4], m[5]) if m[4] else None, note)
        elif m := re.fullmatch(rf"\s+({END}) -> (\w+) when (.+)", line):
            b.arcs.append(Arc(m[1], m[2], None, True, m[3]))
        elif m := re.fullmatch(rf"\s+({END}) -> ({END})", line):
            a, c = m.groups()
            ta, tc = a.split(".")[0], c.split(".")[0]
            if ta in b.uses:
                b.arcs.append(Arc(c, ta, a.split(".")[1] if "." in a else None, False))
            elif tc in b.uses:
                b.arcs.append(Arc(a, tc, c.split(".")[1] if "." in c else None, True))
            else:
                raise SyntaxError(f"{path.name}: neither end is a transition: {line!r}")
        else:
            raise SyntaxError(f"{path.name}: {line!r}")
    return b


class World:
    """runs/ (its Processors with Ports, its legacy routines, its Records and
    enums) and the bundles here."""

    def __init__(self, bundles: dict[str, Bundle]):
        self.bundles = bundles
        paths = sorted((ROOT / "runs").glob("*.runs")) + sorted((ROOT / "runs").glob("*.runs-prim"))
        self.prog = runs.load(paths)
        self.text: dict[str, str] = {}
        for p in paths:
            for m in re.finditer(r"^(?:\w+ )?(?:processor|network) (\w+).*\n((?:[ #].*\n?)*)", p.read_text(), re.M):
                self.text[m[1]] = m[0]
        declared = "\n".join(f.read_text() for f in sorted((ROOT / "pdp1").glob("*.toml")))
        self.declared = set(re.findall(r'routine = "(\w+)"', declared))
        self.storage = tomllib.loads((HERE / "storage.toml").read_text())

    def sig(self, name: str) -> Sig:
        if name == "copy":
            return Sig([("in", "source"), ("out", "target")], "copy")
        if name in self.bundles:
            return Sig([(d, n) for d, n, _ in self.bundles[name].ports], "bundle")
        if name in self.prog.templates:
            return Sig([(p.direction, p.name) for p in self.prog.templates[name].ports.values()], "port")
        assert name in self.prog.routines, f"no routine {name}"
        return Sig([], "legacy")

    def record_of(self, kind: str):
        return self.prog.records.get(kind)

    def network(self, name: str, uses: int) -> bool:
        """A bundle is its own network when the declarations name it or more
        than one transition uses it; otherwise it is laid out where it is used."""
        return name in self.declared or uses > 1


def base(place: str) -> str:
    return re.split(r"[\[.]", place)[0]


def entry(place: str):
    m = re.fullmatch(r"(\w+)\[(\w+)\]\.(\w+)", place)
    return m.groups() if m else None


# ----------------------------------------------------------------- check

def kind_of(w: World, b: Bundle, place: str) -> str:
    if e := entry(place):
        rec = w.record_of(kind_of(w, b, e[0]))
        assert rec and e[2] in rec.fields, f"{b.name}: {place}: no such entry field"
        return rec.fields[e[2]][0]
    if place in b.boundary:
        return b.boundary[place]
    if place in b.places:
        return b.places[place]
    rec, f = place.split(".")
    return w.prog.records[rec].fields[f][0]


def check(w: World, b: Bundle) -> None:
    for a in b.arcs:
        kind_of(w, b, a.place)
        assert a.place.split(".")[0] in w.prog.records or base(a.place) in b.boundary or base(a.place) in b.places, \
            f"{b.name}: {a.place} is no place"
    for t, u in b.uses.items():
        s = w.sig(u.routine)
        ins = sorted(a.io for a in b.arcs if a.transition == t and a.into and a.io)
        outs = sorted(a.io for a in b.arcs if a.transition == t and not a.into and a.io)
        assert ins == sorted(s.inputs), f"{b.name}.{t}: inputs wired {ins}, {u.routine} has {s.inputs}"
        assert outs == sorted(s.outputs), f"{b.name}.{t}: outputs wired {outs}, {u.routine} has {s.outputs}"
        if s.kind == "legacy":
            assert not any(a.io for a in b.arcs if a.transition == t), f"{b.name}.{t}: a legacy routine has no Ports"
        if s.kind == "bundle":
            inner = w.bundles[u.routine]
            for a in b.arcs:
                if a.transition == t and a.io:
                    want = inner.boundary[a.io]
                    assert kind_of(w, b, a.place) == want, f"{b.name}.{t}.{a.io}: {a.place} is not {want}"
    g = guards(b)
    for place in {a.place for a in b.arcs if not a.into}:
        writers = [a.transition for a in b.arcs if not a.into and a.place == place]
        sides = [g[t] for t in writers]
        assert len(sides) == len(set(sides)), f"{b.name}: {place} written twice on one branch: {writers}"
        assert len(writers) < 2 or all(sides), f"{b.name}: {place}: an unguarded writer beside a guarded one"
    for place in {a.place for a in b.arcs if not a.into if entry(a.place)}:
        whole = [a.transition for a in b.arcs if not a.into and a.place == base(place)]
        part = [a.transition for a in b.arcs if not a.into and a.place == place]
        assert not {g[t] for t in whole} & {g[t] for t in part}, f"{b.name}: {place} written whole and in part"
    tests: dict[str, set] = {}
    for a in b.arcs:
        if a.guard:
            tests.setdefault(a.place, set()).add(a.guard)
    for place, ts in tests.items():
        eq = all(t.startswith("== ") for t in ts)
        assert eq or ("else" in ts and len(ts) == 2), f"{b.name}: {place}: {sorted(ts)} is not a test and its else"


def guards(b: Bundle) -> dict[str, tuple[str, str] | None]:
    """A transition's guard: its own guard arc, else the guard of the one
    branch that writes its inputs (a value exists only on that branch)."""
    own = {a.transition: (a.place, a.guard) for a in b.arcs if a.guard}
    out: dict = {}

    def of(t):
        if t not in out:
            out[t] = own.get(t)
            if out[t] is None:
                for a in b.arcs:
                    if a.transition == t and a.into and not a.guard:
                        ws = {of(x) for x in writers(b, a.place)}
                        if len(ws) == 1 and (x := ws.pop()):
                            out[t] = x
        return out[t]
    for t in b.uses:
        of(t)
    return out


def writers(b: Bundle, place: str) -> list[str]:
    """Inside the bundle, a value's writers. A boundary name read is the in
    value, which nothing inside writes. An entry of an inner value is
    written by what writes the value or the entry."""
    if base(place) in b.boundary:
        return []
    return sorted({a.transition for a in b.arcs if not a.into and a.place in (place, base(place))})


# ----------------------------------------------------------------- order

NAMES_BACKWARD = False     # names break the last ties backward: ../order/walk.py's proof that they decide nothing
TESTS_LAST = True          # False leaves the rule's guard fact out (../order/walk.py's planted defect)


def schedule(w: World, b: Bundle) -> list[str]:
    """The order rule of ../order/rule.py (#63): a transition after the
    writers of what it reads and of its guard's value; among the
    transitions that may go next, an unguarded one before a test's branch
    (work that does not depend on a test is done before it). Each branch is
    laid out as one block, its members in the same order. Nothing here reads
    the order of a file's lines or of a Processor's inputs: names break the
    remaining ties, and they decide nothing (NAMES_BACKWARD)."""
    g = guards(b)
    deps = {}
    for t in b.uses:
        reads = [a.place for a in b.arcs if a.transition == t and a.into and not a.guard]
        reads += [g[t][0]] if g[t] else []
        deps[t] = {x for p in reads for x in writers(b, p)} - {t}
    unit = lambda t: g[t][0] if g[t] else t  # noqa: E731
    name = (lambda s: tuple(-ord(c) for c in s)) if NAMES_BACKWARD else (lambda s: tuple(map(ord, s)))

    def ready(pending, done, under):
        return [u for u in pending if all(d in done or unit(d) == u for t in under(u) for d in deps[t])]

    def lay(members, done):
        """members in dependency order, by the rule: a list scheduler."""
        order, pending = [], list(members)
        while pending:
            here = [t for t in pending if deps[t] & set(members) <= set(order) | done]
            t = min(here, key=lambda t: (TESTS_LAST and g[t] is not None, name(t)))
            order.append(t)
            pending.remove(t)
        return order
    order, done = [], set()
    units = sorted({unit(t) for t in b.uses})
    members = lambda u: [t for t in b.uses if unit(t) == u]  # noqa: E731
    while units:
        here = ready(units, done, members)
        u = min(here, key=lambda u: (TESTS_LAST and u not in b.uses, name(u)))
        units.remove(u)
        if u in b.uses:
            order.append(u)
            done.add(u)
            continue
        for side in sorted({g[t] for t in members(u)}, key=lambda x: (x[1] == "else", x)):
            block = lay([t for t in members(u) if g[t] == side], done)
            order += block
        done |= set(members(u))
    return order


# ----------------------------------------------------------------- storage

class Storage:
    """Where each value lives on the PDP-1. A fresh value takes its
    predecessor's word: the two ends of an inout, and a copy's source and
    target, share one. An entry lives in its collection's word for it; the
    boundary where the user's wires put it (`at`); anything else where
    storage.toml says."""

    def __init__(self, w: World, b: Bundle, at: dict[str, str]):
        self.b, self.at = b, at
        parent: dict[str, str] = {}

        def find(p):
            parent.setdefault(p, p)
            while parent[p] != p:
                p = parent[p]
            return p

        def rank(p):           # the root names where the class lives
            return (0 if entry(p) or p in at or p in b.boundary else 1 if f"{b.name}.{p}" in w.storage else 2, p)
        for t, u in b.uses.items():
            s = w.sig(u.routine)
            pairs = [("source", "target")] if s.kind == "copy" else [(n, n) for n in s.inout]
            for i, o in pairs:
                ends = [find(a.place) for a in b.arcs if a.transition == t and ((a.into and a.io == i) or (not a.into and a.io == o))]
                x, y = sorted(ends, key=rank)
                parent[y] = x
        self.find, self.w = find, w

    def __call__(self, place: str) -> str:
        if e := entry(place):
            return f"{self(e[0])}.{e[2]}[{self.at.get(e[1], e[1])}]"
        if place in self.at:
            return self.at[place]
        if "." in place and place.split(".")[0] in self.w.prog.records:
            return place
        root = self.find(place)
        if root != place:
            return self(root)
        key = f"{self.b.name}.{place}"
        assert key in self.w.storage, f"{self.b.name}: {place} has no word"
        return self.w.storage[key]


def hazards(w: World, b: Bundle, order: list[str], at: Storage) -> list[str]:
    """On every branch, in the derived order: when a transition reads a
    value, its word still holds it. A word nothing wrote holds the in value;
    a copy leaves its word holding both values; a collection written whole
    takes its entries' words too."""
    g = guards(b)
    places = sorted({x[0] for x in g.values() if x})

    def whole(p):
        return not entry(p) and w.record_of(kind_of(w, b, p)) is not None

    def ident(place, written):
        if base(place) in b.boundary:
            return ("out" if written else "in", place)
        return ("in" if "." in place and not entry(place) else "", place)

    bad = []
    for choice in itertools.product(*[sorted({x[1] for x in g.values() if x and x[0] == p}) for p in places]):
        side = set(zip(places, choice))
        holds: dict[str, set] = {}

        def ok(place):
            v, k = ident(place, False), at(place)
            parts = whole(place) and any(x.startswith(k + ".") for x in holds)
            if k in holds:
                return v in holds[k] and not parts
            if (e := entry(place)) and at(e[0]) in holds:
                return ident(e[0], False) in holds[at(e[0])]
            return v[0] == "in" and not parts

        for t in order:
            if g[t] and g[t] not in side:
                continue
            reads = [a for a in b.arcs if a.transition == t and a.into]
            for a in reads:
                if not ok(a.place):
                    k = at(a.place)
                    bad.append(f"{b.name} {choice}: {t} reads {a.place}, but {k} holds {sorted(holds.get(k, ['in']))}")
            copy = w.sig(b.uses[t].routine).kind == "copy"
            for a in b.arcs:
                if a.transition == t and not a.into:
                    k, v = at(a.place), ident(a.place, True)
                    holds[k] = ({ident(next(a.place for a in reads if a.io == "source"), False), v} | holds.get(k, set())) if copy else {v}
                    if whole(a.place) and not copy:
                        for x in [x for x in holds if x.startswith(k + ".")]:
                            del holds[x]
    return bad


# ----------------------------------------------------------------- emit

def align(line: str, note: str) -> str:
    return f"{line:<60}# {note}" if note else line


class Emit:
    def __init__(self, w: World):
        self.w = w
        used, todo = set(), ["object_walk"]
        while todo:
            n = todo.pop()
            if n not in used:
                used.add(n)
                todo += [u.routine for u in w.bundles[n].uses.values() if u.routine in w.bundles]
        self.count = {n: sum(u.routine == n for b in used for u in w.bundles[b].uses.values()) for n in w.bundles}
        self.networks: dict[str, str] = {}
        self.orders: dict[str, list[str]] = {}
        self.bad: list[str] = []

    def bundle(self, b: Bundle, at: dict[str, str], pad: str) -> list[str]:
        st = Storage(self.w, b, at)
        order = schedule(self.w, b)
        self.orders[b.name] = order
        self.bad += [x for x in hazards(self.w, b, order, st) if x not in self.bad]
        g = guards(b)
        out: list[str] = []
        i = 0
        while i < len(order):
            t = order[i]
            if g[t] is None:
                out += self.transition(b, t, st, pad); i += 1; continue
            place = g[t][0]
            group = []
            while i < len(order) and g[order[i]] and g[order[i]][0] == place:
                group.append(order[i]); i += 1
            out += self.branches(b, place, group, st, pad)
        return out

    def branches(self, b, place, group, st, pad):
        g = guards(b)
        tests = sorted({g[t][1] for t in group}, key=lambda x: x == "else")
        arms = {x: [l for t in group if g[t][1] == x for l in self.transition(b, t, st, pad + "  ")] for x in tests}
        word = st(place)
        if all(x.startswith("== ") for x in tests):
            enum = kind_of(self.w, b, place)
            out = [f"{pad}match {word}:"]
            for m in self.w.prog.enums[enum]:
                body = arms.get(f"== {m}")
                if not body:
                    out.append(f"{pad}  {m}: unreachable")
                else:
                    assert len(body) == 1, f"{b.name}: the arm {m} is more than one line"
                    out.append(f"{pad}  {m}: {body[0].strip()}")
            return out
        test = " and ".join(f"{word} {c.strip()}" for c in tests[0].split(" and "))
        out = [f"{pad}if {test}:"] + arms[tests[0]]
        if len(tests) > 1 and arms[tests[1]]:
            out += [f"{pad}else:"] + arms[tests[1]]
        assert arms[tests[0]], f"{b.name}: the {tests[0]} branch is empty"
        return out

    def transition(self, b: Bundle, t: str, st: Storage, pad: str) -> list[str]:
        u = b.uses[t]
        s = self.w.sig(u.routine)
        args = [st.at.get(x, x) for x in u.args]
        call = f"{u.routine}({', '.join(args)})" if args else u.routine
        wire = {}
        for a in b.arcs:
            if a.transition == t and a.io:
                wire.setdefault(a.io, {})["in" if a.into else "out"] = st(a.place)
        if s.kind == "copy":
            assert wire["source"]["in"] == wire["target"]["out"], f"{b.name}.{t}: a copy between two words"
            return []
        if s.kind == "legacy":
            for a in b.arcs:
                if a.transition == t and not a.guard:
                    word = st(a.place)
                    named = re.sub(r"\[\w+\]", "", word)
                    assert named in self.w.text[u.routine] or self.mentions(u.routine, named), \
                        f"{b.name}.{t}: {u.routine} does not name {word}"
            return [align(f"{pad}run {call}", u.comment)]
        for n, ends in wire.items():
            assert len(set(ends.values())) == 1, f"{b.name}.{t}.{n}: in and out in two words {ends}: a fresh word costs"
        if s.kind == "port":
            return [align(f"{pad}run {u.routine}", u.comment)] + [f"{pad}  {n}: {wire[n].get('in', wire[n].get('out'))}"
                                                                   for _, n in s.ports]
        inner = self.w.bundles[u.routine]
        at = {n: next(iter(wire[n].values())) for _, n, _ in inner.ports}
        params = dict(zip(inner.params, args))
        if u.fold:
            params[u.fold[0]] = u.fold[0]
        if self.w.network(u.routine, self.count[u.routine]):
            self.make_network(inner, at)
            return [align(f"{pad}run {call}", u.comment)]
        body_pad = pad + "  " if u.fold else pad
        body = self.bundle(inner, {**at, **{p: v for p, v in params.items() if p != v}}, body_pad)
        if u.fold:
            return [align(f"{pad}for {u.fold[0]} in {u.fold[1]}:", u.comment)] + body
        return body

    def mentions(self, routine: str, record: str) -> bool:
        """A legacy Network names a word through the routines it runs."""
        text = self.w.text[routine]
        return any(self.mentions(r, record) for r in re.findall(r"run (\w+)", text) if r in self.w.text and r != routine) \
            or record.split(".")[0] in text

    def make_network(self, b: Bundle, at: dict[str, str]) -> None:
        params = f"({', '.join(b.params)})" if b.params else ""
        body = self.bundle(b, at, "  ")
        text = "\n".join([align(f"network {b.name}{params}", b.comment)] + body) + "\n"
        assert self.networks.get(b.name, text) == text, f"{b.name}: its uses wire it two ways"
        self.networks[b.name] = text


def generate(bundles: dict[str, Bundle]) -> Emit:
    w = World(bundles)
    for b in bundles.values():
        check(w, b)
    e = Emit(w)
    root = bundles["object_walk"]
    e.make_network(root, {n: w.storage[f"object_walk.{n}"] for _, n, _ in root.ports})
    return e


def load_all(over: Path | None = None) -> dict[str, Bundle]:
    """The bundles here; a file of the same name in `over` replaces one."""
    files = {f.name: f for f in sorted(HERE.glob("*.net"))}
    files.update({f.name: f for f in sorted(over.glob("*.net"))} if over else {})
    return {b.name: b for b in map(parse, files.values())}


HOMES = {"object_walk": "frame.runs", "calc": "frame.runs", "torpedo": "objects.runs"}


def region(text: str, name: str) -> tuple[int, int]:
    m = re.search(rf"^network {name}\b.*\n(?:  .*\n)*", text, re.M)
    return m.start(), m.end()


def option(name: str) -> Path | None:
    return Path(sys.argv[sys.argv.index(name) + 1]).resolve() if name in sys.argv else None


def main() -> int:
    bundles = load_all(option("--dir"))
    into = option("--into") or ROOT / "runs"
    write = "--write" in sys.argv or option("--into") is not None
    e = generate(bundles)
    for name, order in e.orders.items():
        print(f"{name}: {', '.join(order)}")
    for seed in range(50):
        r = random.Random(seed)
        shuffled = {}
        for n, b in bundles.items():
            shuffled[n] = Bundle(b.name, b.params, b.ports, dict(r.sample(list(b.places.items()), len(b.places))),
                                 dict(r.sample(list(b.uses.items()), len(b.uses))), r.sample(b.arcs, len(b.arcs)), b.comment)
        assert generate(shuffled).networks == e.networks, f"shuffle {seed} changed the source"
    print("the same source for 50 shuffles of every file")
    if e.bad:
        print("a word is overwritten before it is read:", *e.bad, sep="\n  ")
        return 1
    print("no value is read after the next one takes its word")
    differ = 0
    for name, text in e.networks.items():
        path = into / HOMES[name]
        old = path.read_text()
        s, t = region(old, name)
        if old[s:t] != text:
            if write:
                path.write_text(old[:s] + text + old[t:])
                print(f"wrote {name} into {path}")
            else:
                print(f"{name}: runs/{HOMES[name]} differs from the generated source:\n{text}")
                differ = 1
        else:
            print(f"{name}: runs/{HOMES[name]} is the generated source")
    code = runsc.build(runs.program(into))
    print(runsc.build.said.strip().splitlines()[-1])
    return differ or code


if __name__ == "__main__":
    sys.exit(main())
