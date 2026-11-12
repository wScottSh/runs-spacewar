"""Measure the order freedom of each arithmetic graph and test the rules.

  uv run -q python docs/prototypes/graph-format/order/run.py [routine ...] [--n N]

For each routine: how many orders the graph allows, how many the stored
words allow, how many distinct sources those give and what runsc makes of
each; then the order each rule picks, with every Processor's inputs as
written and reversed, and names breaking ties forward and backward. Last,
the Evaluator against SIMH on the picked order's two sources. Needs
build/oracle.lst, build/oracle.rim and build/pdp1."""
from __future__ import annotations

import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arith  # noqa: E402
import graph  # noqa: E402
import orders  # noqa: E402
import rule  # noqa: E402


def freedom(g, sigs, r) -> None:
    allowed = list(orders.allowed(g))
    sources: dict[str, list] = {}
    for o in allowed:
        s, hazard = orders.source_of(g, sigs, o, r)
        if not hazard:
            sources.setdefault(s, []).append(o)
    print(f"  orders the graph allows: {len(allowed)}; the stored words allow: "
          f"{sum(map(len, sources.values()))}; distinct sources: {len(sources)}")
    seen = Counter()
    for s, os_ in sources.items():
        out = orders.compile_order(g, sigs, os_[0], r)
        what = "refused" if out.refused else "identical" if out.identical else "differs"
        seen[what] += 1
        if what != "refused":
            print(f"    {what}: {out.verdict()}  ({len(os_)} orders)\n      {' '.join(os_[0])}")
    print(f"  runsc: {dict(seen)}")


def evaluate(g, sigs, r, o, n: int) -> int:
    failed = 0
    for shared in (False, True):
        graph.BOUNDARY = r.call
        source = arith.emit(g, sigs, list(o), arith.Storage(g, sigs, shared, r.call))
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            arith.splice(tmp, r, source, shared)
            failed |= arith.evaluate(tmp, r, shared, n)
    return failed


def shuffled(g, seed: int):
    r = random.Random(seed)
    return graph.Graph(g.name, r.sample(g.places, len(g.places)),
                       dict(r.sample(list(g.transitions.items()), len(g.transitions))), r.sample(g.arcs, len(g.arcs)))


def main(names: list[str], n: int) -> int:
    failed = 0
    for name in names:
        r = arith.ROUTINES[name]
        arith.REVERSED = False
        g = arith.load(r)
        sigs = arith.signatures()
        graph.BOUNDARY = r.call
        graph.check(g, sigs)
        print(f"{name}:")
        freedom(g, sigs, r)
        picked = set()
        for reversed_ in (False, True):
            arith.REVERSED = reversed_
            label = "in, inout and out lines reversed in every file" if reversed_ else "files as written"
            sigs = arith.signatures()
            graph.BOUNDARY = r.call
            today = graph.schedule(g, sigs)
            out = orders.compile_order(g, sigs, today, r)
            print(f"  today's rule (a Processor's input order), {label}: {out.verdict()}\n    {' '.join(today)}")
            first = None
            for backward in (False, True):
                out = rule.order(g, sigs, r, backward)
                first = first or out.order
                picked.add(out.order)
                failed |= not out.identical
                print(f"  the rule, {label}, names {'backward' if backward else 'forward'}: "
                      f"{out.verdict()} ({out.tried} orders tried)\n    {' '.join(out.order)}")
            moved = [s for s in range(5) if rule.order(shuffled(g, s), sigs, r).order != first]
            failed |= bool(moved)
            print(f"  the rule, {label}, 5 shuffles of the network file: "
                  f"{'the same order' if not moved else f'a different order for shuffles {moved}'}")
        arith.REVERSED = False
        sigs = arith.signatures()
        for o in sorted(picked):
            failed |= evaluate(g, sigs, r, o, n)
    return failed


if __name__ == "__main__":
    args = sys.argv[1:]
    n = 2000
    if "--n" in args:
        i = args.index("--n")
        n = int(args[i + 1])
        del args[i:i + 2]
    sys.argv[1:] = []                          # the SIMH checks read sys.argv
    sys.exit(main(args or list(arith.ROUTINES), n))
