"""G1 for the XCT functions of the constants table (lift/tunables.c): the
native build against SIMH executing the same word of the oracle binary with
`xct`, call by call, comparing AC (and IO for the AC:IO scalers).

Domains: the AC scalers (tvl, sac, the) over every input word; the
constants (tno, rlt, tlf, mhs, hd1, hd2, hd3) over 1000 seeded random
AC:IO pairs, since they read neither; the pair scalers (hr1, hr2) over
every edge pair plus 100000 seeded random AC:IO pairs.

Usage: uv run python tools/check-tunables-reference.py"""
import sys

from oracle_check import ROOT, Inputs, check, edges, seeded
from pdp1cc import dialect, front, ir

LIFT = "lift/tunables.c"
N = 100_000


def every_word(seed: int) -> list[Inputs]:
    return [Inputs(a, i) for a, i in zip(range(1 << ir.WORD_BITS), seeded(seed, 1 << ir.WORD_BITS))]


def random_pairs(seed: int, n: int) -> list[Inputs]:
    return [Inputs(a, i) for a, i in zip(seeded(seed, n), seeded(seed + 1, n))]


def main() -> int:
    sigs = dialect.lower_unit(front.parse(ROOT / LIFT)).signatures
    failed = 0
    for n, sig in enumerate(s for s in sigs.values() if s.conv is ir.Conv.XCT):
        kinds = [p.kind for p in sig.params]
        if kinds == [ir.ParamKind.AC]:
            calls, domain = every_word(n), "every AC word"
        elif kinds == []:
            calls, domain = random_pairs(n, 1000), "1000 seeded random AC:IO pairs"
        else:
            e = edges()
            calls = [Inputs(a, i) for a in e for i in e] + random_pairs(n, N)
            domain = f"{len(e) ** 2} edge pairs + {N} seeded random AC:IO pairs"
        failed |= check(sig.sym, [LIFT], sig.name, calls, domain)
    return failed


if __name__ == "__main__":
    sys.exit(main())
