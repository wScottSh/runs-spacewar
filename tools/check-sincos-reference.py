"""G1 for sine (sin) and cosine (cos): lift/multiply.c and lift/sincos.c
built natively against SIMH running sin and cos in the oracle binary, at
every input word of the documented range -2 pi .. 2 pi, that is
-0311040 .. 0311040 including -0, with random IO on entry.

Usage: uv run python tools/check-sincos-reference.py"""
import sys

from oracle_check import Inputs, check, neg, seeded

TWO_PI = 0o311040


def calls(seed: int) -> list[Inputs]:
    words = list(range(TWO_PI + 1)) + [neg(v) for v in range(TWO_PI + 1)]
    return [Inputs(a, i) for a, i in zip(words, seeded(seed, len(words)))]


def main() -> int:
    domain = "every word in -0311040..0311040, both zeros"
    failed = check("sin", ["lift/multiply.c", "lift/sincos.c"], "sine", calls(1962), domain)
    failed |= check("cos", ["lift/multiply.c", "lift/sincos.c"], "cosine", calls(1963), domain)
    return failed


if __name__ == "__main__":
    sys.exit(main())
