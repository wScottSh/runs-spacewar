"""G1 for multiply (mpy) and integer_multiply (imp): lift/multiply.c built
natively against SIMH running mpy and imp in the oracle binary. Inputs: every
pair of edge values (0, -0, +-max, +-1, +-powers of two) plus 100000 seeded
random pairs, with random IO on entry.

Usage: uv run python tools/check-multiply-reference.py"""
import sys

from oracle_check import Inputs, check, edges, seeded

N = 100_000


def calls(seed: int) -> list[Inputs]:
    e = edges()
    pairs = [(a, b) for a in e for b in e]
    pairs += list(zip(seeded(seed, N), seeded(seed + 1, N)))
    io = seeded(seed + 2, len(pairs))
    return [Inputs(a, i, b) for (a, b), i in zip(pairs, io)]


def main() -> int:
    domain = f"{len(edges()) ** 2} edge pairs + {N} seeded random pairs"
    failed = check("mpy", ["lift/multiply.c"], "multiply", calls(1962), domain)
    failed |= check("imp", ["lift/multiply.c"], "integer_multiply", calls(1963), domain)
    return failed


if __name__ == "__main__":
    sys.exit(main())
