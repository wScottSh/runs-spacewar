"""The multiply and integer_multiply network files (runs/arithmetic/)
against SIMH running mpy and imp in the oracle image.

Inputs: every pair of edge values (0, -0, +-max, +-1, +-powers of two), the
nine pairs of the observed mpy and imp vectors, and N seeded
random pairs (N defaults to 100000), with random IO on entry. Compared per
call: the result registers, the routine's own words (mpy, mp2, imp), and
where the routine returned (one word past the call, past the second factor).

Run from the repository root:
  uv run python tools/check_multiply.py [N]"""
from __future__ import annotations

import json
import sys

import pdp1
import runs
from oracle_check import edges, oracle_symbols, seeded
from pdp1cc.gate import simh
from pdp1cc.gate.simh import Inputs

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
VECTORS = pdp1.ROOT / "oracle"


def pairs(seed: int, observed: str) -> list[tuple[int, int]]:
    e = edges()
    vectors = [json.loads(line) for line in (VECTORS / observed).read_text().splitlines()]
    return [(a, b) for a in e for b in e] + [(int(v["f1"], 8), int(v["f2"], 8)) for v in vectors] \
        + list(zip(seeded(seed, N), seeded(seed + 1, N)))


def check(label: str, entry: str, call: str, seed: int, observed: str, outputs) -> int:
    """outputs(machine, outcome) -> [(what, simh, runs)] for one call."""
    sym = oracle_symbols()
    cases = pairs(seed, observed)
    io = seeded(seed + 2, len(cases))
    watch = ["mpy", "mp2", "imp"]
    want = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym[entry], [Inputs(a, i, b) for (a, b), i in zip(cases, io)],
                        byname=True, watch=[sym[w] for w in watch])
    m = runs.Machine(runs.program(runs.source()))
    differ = 0
    for (a, b), w in zip(cases, want):
        m.state[call]["entry"], m.state[call]["factor"] = runs.W(a), runs.W(b)
        m.run(label)
        words = dict(zip(watch, w.watched))
        bad = [f"{what} simh {s:06o} runs {r:06o}" for what, s, r in outputs(m, w, words) if s != r]
        if w.returned_past != 1:
            bad.append(f"returned past {w.returned_past}")
        if bad:
            differ += 1
            if differ <= 5:
                print(f"  {label}({a:06o}, {b:06o}): " + "; ".join(bad))
    print(f"{label}: {len(cases)} calls, {len(cases) - differ} match, {differ} differ")
    return 1 if differ or len(want) != len(cases) else 0


def main() -> int:
    def mpy(m, w, words):
        c = m.state["multiply_call"]
        return [("AC", w.ac, c["partial"].v), ("IO", w.io, c["low"].v),
                ("mp2", words["mp2"], c["partial"].v), ("mpy", words["mpy"], c["entry"].v)]

    def imp(m, w, words):
        c, i = m.state["multiply_call"], m.state["integer_multiply_call"]
        return [("AC", w.ac, i["product"].v), ("imp", words["imp"], i["entry"].v),
                ("mp2", words["mp2"], c["partial"].v), ("mpy", words["mpy"], c["entry"].v)]

    failed = check("multiply", "mpy", "multiply_call", 1962, "mpy-vectors.jsonl", mpy)
    failed |= check("integer_multiply", "imp", "integer_multiply_call", 1963, "imp-vectors.jsonl", imp)
    return failed


if __name__ == "__main__":
    sys.exit(main())
