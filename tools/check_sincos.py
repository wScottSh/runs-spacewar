"""The sine and cosine Networks of arithmetic.runs-prim against SIMH running
sin and cos in the oracle image, at every input word (2^18 each, not only
the documented -2 pi .. 2 pi), or a seeded sample of N words with the edges
(0, -0, +-max, +-1, +-powers of two, +-pi/2, +-2 pi).

Compared per call: AC, the routine's own words (sin, cos) and multiply's
(mpy, mp2), and where it returned. AC is also compared with the
observed sin and cos vectors, which cover every word.

Run from the repository root:
  uv run python tools/check_sincos.py [N]"""
from __future__ import annotations

import json
import random
import sys

import pdp1
import runs
from oracle_check import edges, neg, oracle_symbols, seeded
from pdp1cc.gate import simh
from pdp1cc.gate.simh import Inputs

N = int(sys.argv[1]) if len(sys.argv) > 1 else None
VECTORS = pdp1.ROOT / "oracle"
WATCH = ["sin", "cos", "mpy", "mp2"]


def words(seed: int) -> list[int]:
    if N is None:
        return list(range(1 << 18))
    angles = [0o62210, 0o311040, 0o311041, 0o311037]
    return edges() + angles + [neg(a) for a in angles] + random.Random(seed).sample(range(1 << 18), N)


def check(label: str, entry: str, call: str, seed: int) -> int:
    sym = oracle_symbols()
    inputs = words(seed)
    observed = {int(v["in"], 8): int(v["ac"], 8) for v in
                map(json.loads, (VECTORS / f"sincos-{entry}-vectors.jsonl").read_text().splitlines())}
    want = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym[entry],
                        [Inputs(a, i) for a, i in zip(inputs, seeded(seed, len(inputs)))],
                        watch=[sym[w] for w in WATCH], timeout=7200)
    m = runs.Machine(runs.program(runs.source()))
    s, mc = m.state["sine_call"], m.state["multiply_call"]
    differ = saturated = 0
    for a, w in zip(inputs, want):
        m.state[call]["angle"] = runs.W(a)
        m.run(label)
        saturated += s["result"] != s["answer"]
        bad = [f"{what} simh {x:06o} runs {r:06o}" for what, x, r in
               [("AC", w.ac, s["result"].v), ("observed AC", observed[a], s["result"].v),
                ("sin", w.watched[0], s["x"].v), ("cos", w.watched[1], s["answer"].v),
                ("mpy", w.watched[2], mc["entry"].v), ("mp2", w.watched[3], mc["partial"].v),
                ("returned past", w.returned_past, 0)] if x != r]
        if bad:
            differ += 1
            if differ <= 5:
                print(f"  {label}({a:06o}): " + "; ".join(bad))
    print(f"{label}: {len(inputs)} calls, {len(inputs) - differ} match, {differ} differ; "
          f"{saturated} saturate at +-1")
    return 1 if differ or len(want) != len(inputs) else 0


def main() -> int:
    failed = check("sine", "sin", "sine_call", 1962)
    failed |= check("cosine", "cos", "cosine_call", 1963)
    return failed


if __name__ == "__main__":
    sys.exit(main())
