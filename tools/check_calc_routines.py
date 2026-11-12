"""The calc routine Processors of runs/objects/ against SIMH running the
oracle image.

Each call starts from one set of Records: the object table, the spaceship
properties and the random number, all values the game itself can hold. In
SIMH they are deposited where the PDP-1 binding places them, the main
loop's cursors are pointed at the slot, and the routine is entered as the
main loop enters it (jsp). The evaluator runs the Processor on the same
Records. Then every field of those Records and every plotted point, in
order, must be the same.

IO on entry is random on the SIMH side: the original's in_hyperspace shifts
whatever IO holds, and the port claims it all gets pushed out."""
from __future__ import annotations

import copy
import importlib.util
import random
import sys

import pdp1
import runs
from pdp1cc.gate import corpus, simh
from pdp1cc.gate.simh import Inputs
from oracle_check import built_listing

spec = importlib.util.spec_from_file_location("objref", pdp1.ROOT / "tools/check-objects-reference.py")
objref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(objref)

RECORDS = ["objects", "ship_flight", "ship_outlines", "ships", "random"]
CALLS = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
NEG = lambda v: v ^ runs.MASK
COUNTER_EDGES = [NEG(1), NEG(2), runs.MASK, 0, 1, 0o377777, 0o400000, NEG(0o10), NEG(0o100)]


def word(rng) -> runs.W:
    return runs.W(rng.randrange(1 << 18))


def a_state(m: runs.Machine, rng: random.Random, routine: str, ship: bool) -> tuple[int, dict]:
    state = copy.deepcopy({r: m.state[r] for r in RECORDS})
    slot = rng.randrange(2 if ship else 0o30)
    o = state["objects"]
    for s in range(0o30):
        o["routine"][s] = runs.Member("calc_routine", rng.choice(
            ["none", "torpedo", "explosion"] if s >= 2 else
            ["first_spaceship", "second_spaceship", "explosion", "in_hyperspace", "breakout", "none"]))
        for f in ("x", "y", "dx", "dy", "counter", "cycles"):
            o[f][s] = word(rng)
    o["routine"][slot] = runs.Member("calc_routine", routine)
    o["counter"][slot] = runs.W(rng.choice(COUNTER_EDGES + [rng.randrange(1 << 18)] * 4))
    if routine == "explosion":
        o["cycles"][slot] = runs.W(rng.choice([0o2000, 0o20, rng.randrange(0o4000), NEG(rng.randrange(0o4000)),
                                               0o1137, 0o1140, 0o377777, runs.MASK]))
    sh = {**state["ship_flight"], **state["ship_outlines"], **state["ships"]}
    for s in range(2):
        for f in sh:
            sh[f][s] = word(rng)
        sh["saved_routine"][s] = runs.Member("calc_routine", ("first_spaceship", "second_spaceship")[s])
        sh["jumps_left"][s] = runs.W(rng.choice([NEG(1), runs.MASK, 0, NEG(0o10), 0o377777, rng.randrange(1 << 18)]))
        sh["uncertainty"][s] = runs.W(rng.choice([0, 0o340000, 0o377777, 0o400000, NEG(0o40000), runs.MASK,
                                                  rng.randrange(1 << 18)]))
    state["random"]["number"] = word(rng)
    return slot, state


def cursors(slot: int, address: dict, image: dict) -> dict[int, int]:
    out = {}
    for first, cursor, _ in objref.PROPERTIES:
        at = address[first] + (slot % 2 if first in objref.SHIP_ONLY else slot)
        out[address[cursor]] = at if cursor in objref.POOL_CURSORS else image[address[cursor]] & ~0o7777 | at
    return out


def main() -> int:
    prog = runs.program(runs.source())
    b = pdp1.Binding(prog)
    address = objref.oracle_symbols() | objref.built_symbols()
    image = objref.image_words(address)
    display = corpus.display_words(built_listing())
    failed = 0
    for n, (routine, sym, ship) in enumerate([("explosion", "mex", False), ("torpedo", "tcr", False),
                                              ("in_hyperspace", "hp1", True), ("breakout", "hp3", True)]):
        rng = random.Random(0o7100 + n)
        m = runs.Machine(prog)
        cases = [a_state(m, rng, routine, ship) for _ in range(CALLS)]
        places = list(b.places(RECORDS))
        each = [b.deposits(st, RECORDS) | cursors(slot, address, image) for slot, st in cases]
        calls = [Inputs(0, rng.randrange(1 << 18), 0, rng.randrange(1 << 6)) for _ in cases]
        want = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, b.sym[sym], calls, watch=[p[3] for p in places],
                            op="jsp", display=display, each=each)
        differ, outcomes = 0, {}
        for k, ((slot, st), w) in enumerate(zip(cases, want)):
            m.state.update(copy.deepcopy(st))
            m.state["display"] = []
            m.fired = []
            m.run(routine, [slot])
            simh_records = b.read({p[3]: v for p, v in zip(places, w.watched)}, RECORDS)
            bad = [f"{rec}.{fld}[{s}] simh {b.encode(rec, fld, simh_records[rec][fld][s] if s is not None else simh_records[rec][fld]):06o}"
                   f" runs {b.encode(rec, fld, m.state[rec][fld][s] if s is not None else m.state[rec][fld]):06o}"
                   for rec, fld, s, _ in places
                   if (simh_records[rec][fld][s] if s is not None else simh_records[rec][fld])
                   != (m.state[rec][fld][s] if s is not None else m.state[rec][fld])]
            points = [pdp1.point(p) for p in w.plotted]
            if points != m.state["display"]:
                bad.append(f"plotted {len(points)} simh, {len(m.state['display'])} runs")
            if bad:
                differ += 1
                if differ <= 5:
                    print(f"  {routine} call {k} slot {slot}: " + "; ".join(bad)[:400])
            end = m.state["objects"]["routine"][slot].name
            outcomes[end] = outcomes.get(end, 0) + 1
        print(f"{routine}: {len(cases)} calls, {len(cases) - differ} match, {differ} differ; "
              f"{sum(len(w.plotted) for w in want)} points; routine after: {outcomes}")
        failed |= bool(differ)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
