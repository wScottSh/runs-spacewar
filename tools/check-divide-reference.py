"""G1 for divide (dvd) and integer_divide (idv): lift/divide.c built natively
against SIMH running dvd and idv in the oracle binary. Compared per call: AC,
IO and the return point (call+2 on overflow, call+3 otherwise).
Inputs: every (high dividend, divisor) pair of edge values with several low
dividends, plus 100000 seeded random (high, low, divisor) triples, about half
of them overflowing (|high| >= |divisor|).

Usage: uv run python tools/check-divide-reference.py"""
import sys

from oracle_check import MAX, MINUS_ZERO, Inputs, check, edges, seeded

N = 100_000
LOWS = [0, 1, MAX, MAX + 1, MINUS_ZERO]


def calls(seed: int) -> list[Inputs]:
    e = edges()
    out = [Inputs(hi, lo, d) for hi in e for d in e for lo in LOWS]
    out += [Inputs(hi, lo, d) for hi, lo, d in zip(seeded(seed, N), seeded(seed + 1, N), seeded(seed + 2, N))]
    return out


def main() -> int:
    domain = f"{len(edges()) ** 2 * len(LOWS)} edge triples + {N} seeded random triples"
    failed = check("dvd", ["lift/divide.c"], "divide", calls(1962), domain)
    failed |= check("idv", ["lift/divide.c"], "integer_divide", calls(1963), domain)
    return failed


if __name__ == "__main__":
    sys.exit(main())
