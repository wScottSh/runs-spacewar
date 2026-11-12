"""The PDP-1 back end's order among independent transitions, from facts the
graph and the PDP-1 package already hold. For "Order between independent
transitions" (#63).

The back end takes the orders the graph allows (orders.allowed), drops those
that overwrite a word before its value's last read (orders.hazards), and
ranks the rest, transition by transition, by two facts:

  1. tests last: a transition under a guard (a branch of a test) goes after
     every unguarded transition it could go after. Work that does not
     depend on a test is done before the test. (The graph's guards.)
  2. the call form's arrival order: a transition that reads a value the call
     hands over earlier goes first: the jda entry word (`entry`, AC at the
     call), then IO (`io_param`), then the word after the call (`byname`).
     A transition that reads none of them ranks after. (The routine's
     declaration in pdp1/*.toml.)

It compiles the ranked orders in turn and keeps the first that runsc
compiles. Nothing in a Rules file enters: a transition's rank is the set of
places it reads and whether it has a guard, never the order its Processor
lists its inputs, and names break no tie that matters (run.py runs the
names forward and backward)."""
from __future__ import annotations

import tomllib

import arith
import graph
import orders

ARRIVAL = ("entry", "io_param", "byname")
DROP: set[str] = set()     # "tests", "arrival": a fact left out, to show what each one decides


def declaration(routine: str) -> dict:
    found = [p for f in sorted((graph.ROOT / "pdp1").glob("*.toml"))
             for p in tomllib.loads(f.read_text()).get("place", []) if p.get("routine") == routine]
    assert len(found) == 1, f"{routine}: {len(found)} declarations"
    return found[0]


def key(g: graph.Graph, decl: dict):
    rank = {} if "arrival" in DROP else {decl[k]: n for n, k in enumerate(ARRIVAL) if k in decl}
    guard = graph.guards(g)
    reads = {t: {a.place for a in g.arcs if a.transition == t and a.into and a.io} for t in g.transitions}
    return lambda t: ("tests" not in DROP and guard[t] is not None,
                      min((rank.get(p, len(ARRIVAL)) for p in reads[t]), default=len(ARRIVAL)))


def ranked(g: graph.Graph, r: arith.Routine, names_backward: bool = False) -> list[tuple[str, ...]]:
    k = key(g, declaration(r.name))
    name = (lambda t: tuple(-ord(c) for c in t)) if names_backward else (lambda t: tuple(map(ord, t)))
    return sorted(orders.allowed(g), key=lambda o: [(k(t), name(t)) for t in o])


def order(g: graph.Graph, sigs, r: arith.Routine, names_backward: bool = False) -> orders.Outcome:
    """The first ranked order that runsc compiles."""
    tried = 0
    for o in ranked(g, r, names_backward):
        source, hazard = orders.source_of(g, sigs, o, r)
        if hazard:
            continue
        out = orders.compile_order(g, sigs, o, r)
        tried += 1
        if not out.refused:
            out.tried = tried
            return out
    raise AssertionError(f"{r.name}: no order compiles")
