"""The divide and integer_divide network files (runs/arithmetic/)
against SIMH running dvd and idv in the oracle image.

Inputs: every (high dividend, divisor) pair of edge values (0, -0, +-max,
+-1, +-powers of two) with five low dividends, the inputs of the
observed dvd and idv vectors, and N seeded random triples (N defaults to
100000), about half of them overflowing. Compared per call: AC, IO, the
routine's own words (dvd, idv), and where it returned: past the divisor, or
one word further when the quotient fits.

Run from the repository root:
  uv run python tools/check_divide.py [N]"""
from __future__ import annotations

import json
import sys
from collections import Counter

import pdp1
import runs
from oracle_check import MAX, MINUS_ZERO, edges, oracle_symbols, seeded
from pdp1cc.gate import simh
from pdp1cc.gate.simh import Inputs

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
LOWS = [0, 1, MAX, MAX + 1, MINUS_ZERO]
VECTORS = pdp1.ROOT / "oracle"


def calls(seed: int, observed: str, high: str) -> list[Inputs]:
    e = edges()
    vectors = [json.loads(line) for line in (VECTORS / observed).read_text().splitlines()]
    return [Inputs(h, lo, d) for h in e for d in e for lo in LOWS] \
        + [Inputs(int(v[high], 8), int(v.get("lo_div", "0"), 8), int(v["divisor"], 8)) for v in vectors] \
        + [Inputs(*t) for t in zip(seeded(seed, N), seeded(seed + 1, N), seeded(seed + 2, N))]


def check(label: str, entry: str, inputs: list[Inputs], enter) -> int:
    sym = oracle_symbols()
    want = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym[entry], inputs, byname=True, watch=[sym["dvd"], sym["idv"]])
    m = runs.Machine(runs.program(runs.source()))
    c = m.state["divide_call"]
    differ, outcomes = 0, Counter()
    for i, w in zip(inputs, want):
        enter(m, i)
        m.run(label)
        fits = c["outcome"].name == "fits"
        outcomes[c["outcome"].name] += 1
        bad = [f"{what} simh {s:06o} runs {r:06o}" for what, s, r in
               [("AC", w.ac, c["result"].v), ("IO", w.io, c["high"].v),
                ("dvd", w.watched[0], c["high"].v), ("idv", w.watched[1], c["quotient"].v),
                ("returned past", w.returned_past, 2 if fits else 1)] if s != r]
        if bad:
            differ += 1
            if differ <= 5:
                print(f"  {label}({i.ac:06o}, {i.io:06o}, {i.byname:06o}): " + "; ".join(bad))
    print(f"{label}: {len(inputs)} calls, {len(inputs) - differ} match, {differ} differ; {dict(outcomes)}")
    return 1 if differ or len(want) != len(inputs) else 0


def main() -> int:
    def dvd(m, i):
        c = m.state["divide_call"]
        c["high"], c["low"], c["divisor"] = runs.W(i.ac), runs.W(i.io), runs.W(i.byname)

    def idv(m, i):
        c = m.state["integer_divide_call"]
        c["dividend"], c["low"], c["divisor"] = runs.W(i.ac), runs.W(i.io), runs.W(i.byname)

    failed = check("divide", "dvd", calls(1962, "dvd-dvd-vectors.jsonl", "hi_div"), dvd)
    failed |= check("integer_divide", "idv", calls(1963, "dvd-idv-vectors.jsonl", "dividend"), idv)
    return failed


if __name__ == "__main__":
    sys.exit(main())
