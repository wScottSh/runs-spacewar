"""Two levels in the arc-list format: integer_multiply.net uses multiply as one
transition, and multiply.net is multiply's own network file.

A transition names a Processor. The loader finds it as a Processor file
(processors/*.runs-prim) or a network file (*.net beside the parent), and reads
its inputs and outputs from its `in` and `out` lines either way. Each level is
checked and ordered on its own by graph.py. Then both levels go into a scratch
copy of runs/, the Evaluator runs check_multiply (mpy and imp) against SIMH,
and runsc compiles the image.

  uv run -q python docs/prototypes/graph-format/two-level/load.py [N] [parent.net]"""
from __future__ import annotations

import os
import random
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import graph  # noqa: E402

sys.path.insert(0, str(HERE.parent / "arcs"))
import load as one_level  # noqa: E402

graph.EXTRA[:] = [HERE / "processors", HERE / "records"]
NAME = r"\w+(?:\.\w+)?"


def resolve(name: str, near: Path) -> Path:
    found = [f for f in graph.files("processors", "*.runs-prim") if f.stem == name] + list(near.glob(f"{name}.net"))
    assert len(found) == 1, f"{name}: {len(found)} files define it"
    return found[0]


def signature(path: Path) -> graph.Signature:
    """The same for a Processor file and a network file: its in and out lines."""
    s = graph.Signature([], [])
    for line in path.read_text().splitlines():
        if m := re.match(r"\s+(in|out|inout) (\w+):", line):
            d, n = m.groups()
            if d in ("in", "inout"): s.inputs.append(n)
            if d in ("out", "inout"): s.outputs.append(n)
            if d == "inout": s.inout.add(n)
    return s


def load(path: Path) -> graph.Graph:
    """arcs/load.py, plus: an in or out line before the first section, and an
    arc end that is one name (an input or output of this network)."""
    g, section, boundary = graph.Graph("", [], {}, []), None, signature(path)
    for line in path.read_text().splitlines():
        line = line.split("#")[0].rstrip()
        if not line or (section is None and re.match(r"\s+(in|out) \w+:", line)):
            continue
        if line.startswith("network "):
            g.name = line.split()[1]
        elif not line.startswith(" "):
            section = line
        elif section == "places":
            g.places.append(line.strip())
        elif section == "transitions":
            t, p = line.split(":")
            g.transitions[t.strip()] = p.strip()
        elif m := re.fullmatch(rf"\s+({NAME}) -> (\w+) when (.+)", line):
            g.arcs.append(graph.Arc(m[1], m[2], None, True, m[3]))
        elif m := re.fullmatch(rf"\s+({NAME}) -> ({NAME})", line):
            a, b = m.groups()
            if a.split(".")[0] in g.transitions:
                g.arcs.append(graph.Arc(b, *a.split("."), False))
            else:
                g.arcs.append(graph.Arc(a, *b.split("."), True))
        else:
            raise SyntaxError(f"{path.name}: {line!r}")
    ends = boundary.inputs + boundary.outputs
    g.places += [n for n in ends if n not in g.places]
    for a in g.arcs:
        assert "." in a.place or a.place in ends, f"{path.name}: {a.place} is neither a Record field nor an input or output"
    return g


def on_pdp1(g: graph.Graph, call: str) -> graph.Graph:
    """The PDP-1 keeps a network's inputs and outputs in its jda words, the
    fields of <name>_call (as runs/ does for every jda routine). This renames
    each bare input or output to that field; nothing in the network file says it."""
    def at(p):
        return p if "." in p else f"{call}.{p}"
    ends = sorted(p for p in g.places if "." not in p)
    assert sorted(graph.record_fields()[call]) == ends, f"{call}: fields are not {g.name}'s inputs and outputs {ends}"
    return graph.Graph(g.name, [at(p) for p in g.places], dict(g.transitions),
                       [graph.Arc(at(a.place), a.transition, a.io, a.into, a.guard) for a in g.arcs])


def order(g: graph.Graph, sigs, boundary: str) -> list[str]:
    graph.BOUNDARY = boundary
    graph.check(g, sigs)
    first = graph.schedule(g, sigs)
    for seed in range(50):
        r = random.Random(seed)
        h = graph.Graph(g.name, r.sample(g.places, len(g.places)),
                        dict(r.sample(list(g.transitions.items()), len(g.transitions))), r.sample(g.arcs, len(g.arcs)))
        assert graph.schedule(h, sigs) == first, f"{g.name}: shuffle {seed} changed the order"
    print(f"{g.name}: derived order (same for 50 shuffles of the file):", ", ".join(first))
    return first


def emit_parent(g: graph.Graph, sigs, steps: list[str], bundles: set[str], shared: bool) -> str:
    """Today's RUNS for a level that runs bundles. A `run` passes no values, so
    a bundle's inputs are copied into its jda words before `run`, and its
    outputs read from them after. Stored: a place a bundle's output writes is
    that jda word, so nothing is copied out."""
    assert not graph.guards(g) or not any(graph.guards(g).values()), "a guard in a level with bundles: not built"
    wire = {(a.transition, a.io): a.place for a in g.arcs if a.io}
    at = {}
    if shared:
        at = {wire[t, n]: f"{g.transitions[t]}_call.{n}"
              for t in steps if g.transitions[t] in bundles for n in sigs[g.transitions[t]].outputs}
    place = lambda p: at.get(p, p)  # noqa: E731
    body = []
    for t in steps:
        p, s = g.transitions[t], sigs[g.transitions[t]]
        assert not s.inout, f"{t}: an inout in a level with bundles: not built"
        if p in bundles:
            for n in s.inputs:
                body += ["  run copy", f"    source: {place(wire[t, n])}", f"    target: {p}_call.{n}"]
            body.append(f"  run {p}")
            for n in s.outputs:
                if place(wire[t, n]) != f"{p}_call.{n}":
                    body += ["  run copy", f"    source: {p}_call.{n}", f"    target: {place(wire[t, n])}"]
        else:
            body += [f"  run {p}"] + [f"    {n}: {place(wire[t, n])}" for n in s.inputs + s.outputs]
    written = {place(a.place).split(".")[0] for a in g.arcs if not a.into}
    written |= {f"{g.transitions[t]}_call" for t in steps if g.transitions[t] in bundles}
    return "\n".join([f"network {g.name}", f"  writes: {', '.join(sorted(written))}"] + body) + "\n"


def splice(tmp: Path, bundle: str, parent: str, shared: bool) -> None:
    graph.BOUNDARY = "multiply_call"
    graph.splice(tmp, bundle, work_record=not shared)
    prim = tmp / "runs/arithmetic.runs-prim"
    t = prim.read_text()
    start, end = t.index("processor integer_multiply_factors"), t.index("# BBN divide (dvd)")
    prim.write_text(t[:start] + parent + "\n" + t[end:])
    sw = tmp / "runs/spacewar.runs"
    t = sw.read_text()
    m = re.search(r"game record integer_multiply_call\n(  .*\n)+", t)
    sw.write_text(t[:m.start()] + t[m.end():])
    shutil.copy(HERE / "records/integer_multiply_call.runs", tmp / "runs")


def main(n: int, parent_path: Path) -> int:
    parent = load(parent_path)
    sigs = graph.signatures()
    bundles = {}
    for p in parent.transitions.values():
        f = resolve(p, parent_path.parent)
        sigs[p] = signature(f)
        print(f"{p}: {f.name}, inputs {sigs[p].inputs}, outputs {sigs[p].outputs}")
        if f.suffix == ".net":
            bundles[p] = on_pdp1(load(f), f"{p}_call")
    assert list(bundles) == ["multiply"], "this prototype builds one bundle, multiply"
    multiply = bundles["multiply"]
    flat = one_level.load(HERE.parent / "arcs/multiply.net")
    same = (sorted(multiply.places), multiply.transitions, sorted(map(repr, multiply.arcs))) == \
        (sorted(flat.places), flat.transitions, sorted(map(repr, flat.arcs)))
    print("multiply.net, its inputs and outputs in multiply_call, is arcs/multiply.net:", same)

    inner = order(multiply, sigs, "multiply_call")
    outer = order(parent, sigs, "integer_multiply_call")
    failed = 0
    for shared in (False, True):
        graph.BOUNDARY = "multiply_call"
        at = graph.Storage(multiply, sigs, shared)
        if shared and (bad := graph.hazards(multiply, inner, at)):
            print("stored: a word is overwritten before it is read:", *bad, sep="\n  ")
            return 1
        bundle_src = graph.emit(multiply, sigs, inner, at)
        parent_src = emit_parent(parent, sigs, outer, set(bundles), shared)
        what = "stored (places sharing PDP-1 words)" if shared else "written once (every place its own field)"
        print(f"--- {what}\n{parent_src}", end="")
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            splice(tmp, bundle_src, parent_src, shared)
            os.environ["RUNS_SOURCE"] = str(tmp / "runs")
            import check_multiply as cm
            cm.N = n
            failed |= cm.main()
            if shared:
                graph.runsc.BINDINGS = tmp / "pdp1"
                code = graph.runsc.build(graph.runs.program(tmp / "runs"), tmp / "out")
                print(*graph.runsc.build.said.strip().splitlines()[-3:], sep="\n")
                failed |= code
    return failed


if __name__ == "__main__":
    args = sys.argv[1:]
    n = int(args.pop(0)) if args and args[0].isdigit() else 20000
    sys.exit(main(n, Path(args[0]).resolve() if args else HERE / "integer_multiply.net"))
