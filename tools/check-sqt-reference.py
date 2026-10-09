"""G1 for sqt: the native reference build of lift/sqt.c against SIMH running
sqt in the ORACLE binary, over the whole input domain 0..0177777.

Usage: uv run python tools/check-sqt-reference.py"""
import re
import sys
from pathlib import Path

from pdp1cc.gate import reference, simh

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = range(0o200000)


def oracle_symbol(name: str) -> int:
    lst = (ROOT / "build/oracle.lst").read_text(errors="replace")
    return int(re.search(rf"^ {name}\s+([0-7]{{6}})$", lst, re.M).group(1), 8)


def main() -> int:
    native = reference.build(ROOT / "lift/sqt.c", "sqt", ROOT / "build/ref/sqt")
    want = simh.run_jda(ROOT / "build/pdp1", ROOT / "build/oracle.rim", oracle_symbol("sqt"), list(DOMAIN))
    got = reference.run(native, list(DOMAIN))
    bad = [(x, w[0], g[0]) for x, w, g in zip(DOMAIN, want, got) if w[0] != g[0]]
    print(f"sqt: {len(DOMAIN)} inputs 0..{DOMAIN[-1]:o}, {len(DOMAIN) - len(bad)} match, {len(bad)} differ")
    for x, w, g in bad[:10]:
        print(f"  input {x:06o}: oracle {w:06o} native {g:06o}")
    return 1 if bad or len(got) != len(DOMAIN) else 0


if __name__ == "__main__":
    sys.exit(main())
