"""G1 for square_root (sqt): the native reference build of
lift/square_root.c against SIMH running sqt in the ORACLE binary, over the
whole input domain 0..0177777.

Usage: uv run python tools/check-square-root-reference.py"""
import sys

from oracle_check import Inputs, check

DOMAIN = range(0o200000)


def main() -> int:
    return check("square_root", ["lift/square_root.c"], "square_root", [Inputs(x) for x in DOMAIN],
                 f"all inputs 0..{DOMAIN[-1]:o}")


if __name__ == "__main__":
    sys.exit(main())
