"""The arithmetic's network files, loaded, stored on the PDP-1, spliced into a
scratch copy of runs/, and checked against SIMH. For "Order between
independent transitions" (#63). Reuses ../graph.py and ../two-level/load.py.

A transition names a Processor file or a bundle's network file. On the
PDP-1 a bundle's inputs and outputs live in its jda Record, <bundle>_call,
as ../two-level/ does it: the generated source copies a value into the
bundle's word before `run`, and out of it after, unless the value already
lives there."""
from __future__ import annotations

import os
import re
import shutil
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORMAT = HERE.parent
sys.path.insert(0, str(FORMAT))
sys.path.insert(0, str(FORMAT / "two-level"))
import graph  # noqa: E402
import load as two_level  # noqa: E402

graph.EXTRA[:] = [FORMAT / "two-level/processors", FORMAT / "two-level/records", HERE / "processors", HERE / "records"]
PROCESSOR_DIRS = [FORMAT / "processors", FORMAT / "two-level/processors", HERE / "processors"]
RECORD_DIRS = [FORMAT / "records", FORMAT / "two-level/records", HERE / "records"]
BUNDLES = {"multiply": FORMAT / "two-level/multiply.net", "divide": HERE / "divide.net", "sine": HERE / "sine.net"}


@dataclass
class Routine:
    name: str
    net: Path
    call: str                  # the jda Record: the network's inputs and outputs on the PDP-1
    work: str                  # the Record of its own places
    region: tuple[str, str]    # what the network replaces in runs/arithmetic.runs-prim
    replaces: list[str] = field(default_factory=list)   # Records of runs/spacewar.runs it brings its own of
    under: list[str] = field(default_factory=list)      # bundles spliced in with it, from their own graphs


ROUTINES = {
    "multiply": Routine("multiply", BUNDLES["multiply"], "multiply_call", "multiply_work",
                        ("processor multiply  ", "# BBN integer multiply (imp)"), ["multiply_call"]),
    "integer_multiply": Routine("integer_multiply", FORMAT / "two-level/integer_multiply.net",
                                "integer_multiply_call", "integer_multiply_work",
                                ("processor integer_multiply_factors", "# BBN divide (dvd)"),
                                ["integer_multiply_call"], ["multiply"]),
    "divide": Routine("divide", BUNDLES["divide"], "divide_call", "divide_work",
                      ("processor divide  ", "# BBN integer divide (idv)"), ["divide_call"]),
    "integer_divide": Routine("integer_divide", HERE / "integer_divide.net", "integer_divide_call",
                              "integer_divide_work", ("processor integer_divide_dividend", "# The `random` macro"),
                              ["integer_divide_call"], ["divide"]),
    "sine": Routine("sine", BUNDLES["sine"], "sine_call", "sine_work",
                    ("processor sine_reduce", "processor cosine_angle"), ["sine_call"]),
    "cosine": Routine("cosine", HERE / "cosine.net", "cosine_call", "cosine_work",
                      ("processor cosine_angle", "# BBN multiply (mpy)"), ["cosine_call"]),
}


def types(path: Path) -> dict[str, str]:
    """A network file's inputs and outputs and their types."""
    return {m[2]: m[3] for line in path.read_text().splitlines() if (m := re.match(r"\s+(in|out|inout) (\w+): (\w+)", line))}


def copier(bundle: str, name: str) -> str:
    """The Processor that copies a bundle's input or output: copy for a word."""
    kind = types(BUNDLES[bundle])[name]
    return "copy" if kind == "word" else f"copy_{kind}"


def leaves(bundle: str) -> set[str]:
    """The jda Records a run of the bundle writes: its own and its bundles'."""
    used = set(two_level.load(BUNDLES[bundle]).transitions.values()) & set(BUNDLES)
    return {f"{bundle}_call"}.union(*(leaves(b) for b in used))


def declared_skip(routine: str) -> list[str]:
    """The field of the routine's skip return, as pdp1/*.toml declares it."""
    for f in sorted((graph.ROOT / "pdp1").glob("*.toml")):
        for p in tomllib.loads(f.read_text()).get("place", []):
            if p.get("routine") == routine and "skips" in p:
                return [p["skips"][0]]
    return []


def record_file(name: str) -> Path:
    found = [d / f"{name}.runs" for d in RECORD_DIRS if (d / f"{name}.runs").exists()]
    assert len(found) == 1, f"{name}: {found}"
    return found[0]


REVERSED = False      # every Processor file and network file read with its in, inout and out lines reversed


def reversed_lines(text: str) -> str:
    """A Processor or network file with its in, inout and out lines in the
    opposite order."""
    lines = text.splitlines(keepends=True)
    at = [i for i, line in enumerate(lines) if re.match(r"\s+(in|out|inout) \w+:", line)]
    for i, line in zip(at, reversed([lines[i] for i in at])):
        lines[i] = line
    return "".join(lines)


def signature(path: Path) -> graph.Signature:
    if not REVERSED:
        return two_level.signature(path)
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"reversed-{os.getpid()}-{path.name}"
    tmp.write_text(reversed_lines(path.read_text()))
    try:
        return two_level.signature(tmp)
    finally:
        tmp.unlink()


def signatures() -> dict[str, graph.Signature]:
    sigs = {}
    for d in PROCESSOR_DIRS:
        for f in sorted(d.glob("*.runs-prim")):
            sigs[f.stem] = signature(f)
    for name, f in BUNDLES.items():
        sigs[name] = signature(f)
    return sigs


def load(r: Routine) -> graph.Graph:
    """../two-level/load.py's loader; a bare input or output is the field of
    the same name in the network's jda Record."""
    g = two_level.load(r.net)
    at = lambda p: p if "." in p else f"{r.call}.{p}"  # noqa: E731
    return graph.Graph(g.name, [at(p) for p in g.places], dict(g.transitions),
                       [graph.Arc(at(a.place), a.transition, a.io, a.into, a.guard) for a in g.arcs])


class Storage:
    """Where a place lives on the PDP-1. Written once (shared=False): each
    place its own field. Stored, the first that applies:
      the word storage.toml names for it;
      a bundle's output word, for a place a bundle output writes;
      the word of the place an inout replaces, when that is a jda field;
      a bundle's input word, for a place only that bundle input reads;
      else a register value, which runsc keeps in AC or IO."""
    TABLE = tomllib.loads((HERE / "storage.toml").read_text())

    def __init__(self, g: graph.Graph, sigs, shared: bool, call: str):
        self.shared = shared
        parent = {p: p for p in g.places}

        def find(p):
            while parent[p] != p:
                p = parent[p]
            return p
        for t, proc in g.transitions.items():
            for n in sigs[proc].inout:
                a, b = sorted(find(a.place) for a in g.arcs if a.transition == t and a.io == n)
                if b.startswith(call + "."):
                    a, b = b, a
                parent[b] = a
        bundle_end = {}
        for p in g.places:
            outs = {(g.transitions[a.transition], a.io) for a in g.arcs if a.place == p and not a.into
                    and g.transitions[a.transition] in BUNDLES}
            ins = {(g.transitions[a.transition], a.io) for a in g.arcs if a.place == p and a.into and a.io}
            if len(outs) == 1:
                bundle_end[p] = "{}_call.{}".format(*outs.pop())
            elif len(ins) == 1 and next(iter(ins))[0] in BUNDLES and not p.startswith(call + "."):
                bundle_end[p] = "{}_call.{}".format(*ins.pop())
        self.where = {}
        for p in g.places:
            r = find(p)
            w = self.TABLE.get(p) or self.TABLE.get(r) or bundle_end.get(p) \
                or (r if r.startswith(call + ".") else r.split(".")[1])
            self.where[p] = self.TABLE.get(w, w)
        self.owned = sorted({w for w in self.where.values() if "." not in w})

    def __call__(self, place: str) -> str:
        return self.where[place] if self.shared else place

    def word(self, field_: str) -> str:
        """A field of a bundle's jda Record, where it lives."""
        return self.TABLE.get(field_, field_) if self.shared else field_


def steps_of(g: graph.Graph, sigs, order, at):
    """Each transition's statements of today's RUNS: (guard, lines, words
    written, words read, words copied into a bundle's inputs)."""
    guard = graph.guards(g)
    out = []
    for t in order:
        proc, s = g.transitions[t], sigs[g.transitions[t]]
        wire = {}
        for a in g.arcs:
            if a.transition == t and a.io:
                wire.setdefault(a.io, {})["in" if a.into else "out"] = at(a.place)
        written = {wire[o]["out"] for o in s.outputs}
        if proc in BUNDLES:
            lines = []
            for n in s.inputs:
                if wire[n]["in"] != (w := at.word(f"{proc}_call.{n}")):
                    lines += [f"run {copier(proc, n)}", f"  source: {wire[n]['in']}", f"  target: {w}"]
            lines.append(f"run {proc}")
            for n in s.outputs:
                if wire[n]["out"] != (w := at.word(f"{proc}_call.{n}")):
                    lines += [f"run {copier(proc, n)}", f"  source: {w}", f"  target: {wire[n]['out']}"]
            out.append((guard[t], lines, written))
            continue
        if proc == "copy" and wire["source"]["in"] == wire["target"]["out"]:
            continue                                      # the value is already there
        lines, args = [], []
        for n in s.inputs + [o for o in s.outputs if o not in s.inout]:
            w = wire[n]
            if n in s.inout and w["in"] != w["out"]:
                lines += ["run copy", f"  source: {w['in']}", f"  target: {w['out']}"]
            args.append(f"  {n}: {w.get('out', w.get('in'))}")
        out.append((guard[t], lines + [f"run {proc}"] + args, written))
    return out


def emit(g: graph.Graph, sigs, order: list[str], at) -> str:
    """../graph.py's emit, with bundles, and one change for today's compiler:
    an else that only writes the declared skip field (pdp1/*.toml `skips`),
    which the test's own side writes too, is written before the if: the
    skip's other value is no code, and runsc compiles an empty else to a
    jump."""
    steps = steps_of(g, sigs, order, at)
    skip = {at.word(f) for f in declared_skip(g.name)}
    for place in sorted({gd[0] for gd, _, _ in steps if gd}):
        then = [i for i, (gd, _, _) in enumerate(steps) if gd and gd[0] == place and gd[1] != "else"]
        other = [i for i, (gd, _, _) in enumerate(steps) if gd and gd[0] == place and gd[1] == "else"]
        written = set().union(*(steps[i][2] for i in then))
        if then and other and all(steps[i][2] <= written & skip for i in other):
            moved = [(None, steps[i][1], steps[i][2]) for i in other]
            for i in reversed(other):
                del steps[i]
            steps[then[0]:then[0]] = moved
    bundles = set().union(*(leaves(p) for p in g.transitions.values() if p in BUNDLES))
    named = {at(p).split(".")[0] for p in g.places if "." in at(p)} | bundles
    writes = {w.split(".")[0] for _, _, ws in steps for w in ws if "." in w} | bundles
    out = [f"network {g.name}"] + ([f"  reads: {', '.join(sorted(named - writes))}"] if named - writes else [])
    out.append(f"  writes: {', '.join(sorted(writes))}")
    out += [f"  owns {n}: word" for n in at.owned] if at.shared else []
    opened = None
    for gd, lines, _ in steps:
        if gd != opened and gd is not None:
            out.append("  else:" if gd[1] == "else" else f"  if {at(gd[0])} {gd[1]}:")
        opened = gd
        pad = "    " if gd else "  "
        out += [pad + line for line in lines]
    return "\n".join(out) + "\n"


RULE_ORDER: dict[tuple[str, bool], tuple[str, ...]] = {}


def source(name: str, shared: bool) -> str:
    """A routine's generated source in the order the rule picks."""
    r = ROUTINES[name]
    g = load(r)
    sigs = signatures()
    if (name, REVERSED) not in RULE_ORDER:
        import rule
        RULE_ORDER[name, REVERSED] = rule.order(g, sigs, r).order
    graph.BOUNDARY = r.call
    return emit(g, sigs, list(RULE_ORDER[name, REVERSED]), Storage(g, sigs, shared, r.call))


def splice(tmp: Path, r: Routine, text: str, shared: bool, under: dict[str, str] | None = None) -> None:
    """runs/ and pdp1/ into tmp, with the routine's network in place of
    today's, and each bundle under it from its own graph (`under`: name ->
    source; by default the bundle's rule order)."""
    root = graph.ROOT
    shutil.copytree(root / "runs", tmp / "runs")
    shutil.copytree(root / "pdp1", tmp / "pdp1")
    pieces = [(r, text)] + [(ROUTINES[b], (under or {}).get(b) or source(b, shared)) for b in r.under]
    prim = tmp / "runs/arithmetic.runs-prim"
    sw = tmp / "runs/spacewar.runs"
    for routine, src in pieces:
        graph.BOUNDARY = r.call
        t = prim.read_text()
        start, end = t.index(routine.region[0]), t.index(routine.region[1])
        prim.write_text(t[:start] + src + "\n" + t[end:])
        for rec in routine.replaces:
            t = sw.read_text()
            m = re.search(rf"game record {rec}\n(  .*\n)+", t)
            sw.write_text(t[:m.start()] + t[m.end():])
            shutil.copy(record_file(rec), tmp / "runs")
        if not shared:
            shutil.copy(record_file(routine.work), tmp / "runs")
    for d in PROCESSOR_DIRS:
        for f in d.glob("*.runs-prim"):
            (tmp / "runs" / f.name).write_text(reversed_lines(f.read_text()) if REVERSED else f.read_text())
    graph.BOUNDARY = r.call


def evaluate(tmp: Path, r: Routine, shared: bool, n: int) -> int:
    """The routine's SIMH check, run on the scratch copy's RUNS."""
    os.environ["RUNS_SOURCE"] = str(tmp / "runs")
    import runs
    from oracle_check import oracle_symbols
    from pdp1cc.gate import simh
    sym = oracle_symbols()
    if r.name in ("multiply", "integer_multiply"):
        import check_multiply as cm
        cm.N = n

        def mpy(m, w, words):
            c = m.state["multiply_call"]
            return [("AC", w.ac, c["partial"].v), ("IO", w.io, c["low"].v),
                    ("mp2", words["mp2"], c["partial"].v), ("mpy", words["mpy"], c["entry"].v)]

        def imp(m, w, words):
            c, i = m.state["multiply_call"], m.state["integer_multiply_call"]
            return [("AC", w.ac, i["product"].v), ("imp", words["imp"], i["entry"].v),
                    ("mp2", words["mp2"], c["partial"].v), ("mpy", words["mpy"], c["entry"].v)]
        if r.name == "multiply":
            return cm.check("multiply", "mpy", "multiply_call", 1962, "mpy-vectors.jsonl", mpy)
        return cm.check("integer_multiply", "imp", "integer_multiply_call", 1963, "imp-vectors.jsonl", imp)
    if r.name in ("divide", "integer_divide"):
        import check_divide as cd
        cd.N = n
        entry, call, seed, vectors, high = {"divide": ("dvd", "divide_call", 1962, "dvd-dvd-vectors.jsonl", "high"),
                                            "integer_divide": ("idv", "integer_divide_call", 1963,
                                                               "dvd-idv-vectors.jsonl", "dividend")}[r.name]
        inputs = cd.calls(seed, vectors, "hi_div" if r.name == "divide" else "dividend")
        want = simh.run_jda(cd.pdp1.SIMH, cd.pdp1.ORACLE, sym[entry], inputs, byname=True,
                            watch=[sym["dvd"], sym["idv"]])
        m = runs.Machine(runs.program(runs.source()))
        c, d = m.state[call], m.state["divide_call"]
        remainder = "high" if shared else "remainder"      # stored, the remainder is dvd's own word
        differ, outcomes = 0, Counter()
        for i, w in zip(inputs, want):
            c[high], c["low"], c["divisor"] = runs.W(i.ac), runs.W(i.io), runs.W(i.byname)
            m.run(r.name)
            out = d if shared else c
            fits = out["outcome"].name == "fits"
            outcomes[out["outcome"].name] += 1
            bad = [f"{what} simh {s:06o} runs {v:06o}" for what, s, v in
                   [("AC", w.ac, out["result"].v), ("IO", w.io, out[remainder].v),
                    ("dvd", w.watched[0], d[remainder].v), ("idv", w.watched[1], d["quotient"].v),
                    ("returned past", w.returned_past, 2 if fits else 1)] if s != v]
            if bad:
                differ += 1
                if differ <= 5:
                    print(f"  {r.name}({i.ac:06o}, {i.io:06o}, {i.byname:06o}): " + "; ".join(bad))
        print(f"{r.name}: {len(inputs)} calls, {len(inputs) - differ} match, {differ} differ; {dict(outcomes)}")
        return 1 if differ or len(want) != len(inputs) else 0
    import check_sincos as cs
    cs.N = n
    entry, seed = {"sine": ("sin", 1962), "cosine": ("cos", 1963)}[r.name]
    inputs = cs.words(seed)
    want = simh.run_jda(cs.pdp1.SIMH, cs.pdp1.ORACLE, sym[entry], [simh.Inputs(a, 0) for a in inputs],
                        watch=[sym[w] for w in cs.WATCH], timeout=7200)
    m = runs.Machine(runs.program(runs.source()))
    s, mc, c = m.state["sine_call"], m.state["multiply_call"], m.state[r.call]
    work = s if shared or r.name == "cosine" else m.state["sine_work"]
    differ = 0
    for a, w in zip(inputs, want):
        c["angle"] = runs.W(a)
        m.run(r.name)
        result = (s if shared else c)["result"]
        bad = [f"{what} simh {x:06o} runs {v:06o}" for what, x, v in
               [("AC", w.ac, result.v), ("sin", w.watched[0], work["x"].v), ("cos", w.watched[1], work["answer"].v),
                ("mpy", w.watched[2], mc["entry"].v), ("mp2", w.watched[3], mc["partial"].v),
                ("returned past", w.returned_past, 0)] if x != v]
        if bad:
            differ += 1
            if differ <= 5:
                print(f"  {r.name}({a:06o}): " + "; ".join(bad))
    print(f"{r.name}: {len(inputs)} calls, {len(inputs) - differ} match, {differ} differ")
    return 1 if differ or len(want) != len(inputs) else 0
