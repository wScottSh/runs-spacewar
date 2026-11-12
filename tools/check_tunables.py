"""The tunables of tunables.runs-prim and the tunables Record against SIMH
running the oracle image.

Each tunable the original executes with xct is a Processor over handoff.
SIMH executes the word at its address with `xct`, AC and IO set; the
evaluator sets the Processor's input fields to the same AC and IO, fires
it, and its result fields must be AC (and IO) after the xct. Domains, as
check-tunables-reference.py: a scaler of AC over every word;
a constant over 1000 seeded AC:IO pairs, since it reads neither; a scaler
of the AC:IO pair over every pair of edge words and 100,000 seeded pairs.

The tunables kept as numbers are the Record's initial values: each must be
the word at its address in the oracle image.

Run from the repository root:
  uv run python tools/check_tunables.py [N]"""
from __future__ import annotations

import sys
import tomllib

import pdp1
import runs
import runsc
from oracle_check import edges, oracle_symbols, seeded
from pdp1cc.gate import simh
from pdp1cc.gate.simh import Inputs

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
BINDING = pdp1.ROOT / "pdp1/tunables.toml"
# Each XCT Processor: the oracle label of the word the original executes.
SYMBOLS = {"torpedo_supply": "tno", "torpedo_velocity": "tvl", "torpedo_reload_time": "rlt",
           "torpedo_life": "tlf", "spaceship_acceleration": "sac", "torpedo_space_warpage": "the",
           "hyperspace_shots": "mhs", "time_before_breakout": "hd1", "breakout_time": "hd2",
           "hyperfield_recharge_time": "hd3", "hyperspatial_displacement": "hr1",
           "hyperspatial_velocity": "hr2"}


def calls_for(b: runsc.Bound, n: int) -> tuple[list[Inputs], str]:
    if b.io_param:
        e = edges()
        return [Inputs(a, i) for a in e for i in e] + \
            [Inputs(a, i) for a, i in zip(seeded(n, N), seeded(n + 1, N))], f"{len(e) ** 2} edge pairs + {N} seeded"
    if b.ac_param:
        return [Inputs(a, i) for a, i in zip(range(1 << 18), seeded(n, 1 << 18))], "every AC word"
    return [Inputs(a, i) for a, i in zip(seeded(n, 1000), seeded(n + 1, 1000))], "1000 seeded AC:IO pairs"


def check_routine(prog: runs.Program, sym: dict, b: runsc.Bound, n: int) -> int:
    name = b.name
    label = SYMBOLS[prog.copies.get(name, (name,))[0]]      # a copy's label is its template's
    calls, domain = calls_for(b, n)
    want = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym[label], calls, op="xct", timeout=3600)
    m = runs.Machine(prog)
    inputs = [b.ac_param, b.io_param]
    differ = 0
    for c, w in zip(calls, want):
        for f, v in zip(inputs, (c.ac, c.io)):
            if f:
                rec, fld = f.split(".")
                m.state[rec][fld] = runs.W(v)
        m.run(name)
        got = [m.state[rec][fld].v for rec, fld in (f.split(".") for f in b.result)]
        bad = [f"{reg} simh {x:06o} runs {r:06o}" for reg, x, r in zip(("AC", "IO"), (w.ac, w.io), got) if x != r]
        if w.returned_past:
            bad.append(f"returned past {w.returned_past}")
        if bad:
            differ += 1
            if differ <= 5:
                print(f"  {name}(AC {c.ac:06o}, IO {c.io:06o}): " + "; ".join(bad))
    print(f"{name} ({label}): {len(calls)} calls ({domain}), {len(calls) - differ} match, {differ} differ")
    return 1 if differ or len(want) != len(calls) else 0


def check_numbers(prog: runs.Program, sym: dict, places: list[dict]) -> int:
    b = pdp1.Binding(prog)
    fields = [f for p in places for f in p.get("fields", [])]
    at = [b.address(*f.split(".")) for f in fields]
    image = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym["tno"], [Inputs(0, 0)], op="xct", watch=at)[0].watched
    initial = runs.Machine(prog).state
    differ = 0
    for f, word in zip(fields, image):
        rec, fld = f.split(".")
        if initial[rec][fld].v != word:
            differ += 1
            print(f"  {f}: image {word:06o} runs {initial[rec][fld].v:06o}")
    print(f"tunables kept as numbers: {len(fields)} fields, {len(fields) - differ} match the image, {differ} differ")
    return 1 if differ else 0


def main() -> int:
    prog = runsc.pdp1_program()   # the program runsc compiled: one copy a called routine
    sym = oracle_symbols()
    places = tomllib.loads(BINDING.read_text())["place"]
    failed = check_numbers(prog, sym, places)
    # what each XCT routine takes and leaves in AC and IO, as runsc derives it from the text
    bound = runsc.Bindings(prog, sorted(runsc.BINDINGS.glob("*.toml"))).bound
    for n, place in enumerate(p for p in places if p.get("convention") == "XCT"):
        name = place["routine"]           # a routine with Ports: its one copy (runsc copies_of)
        name = next((c for c, (t, _) in prog.copies.items() if t == name), name)
        failed |= check_routine(prog, sym, bound[name], n)
    return failed


if __name__ == "__main__":
    sys.exit(main())
