"""The PDP-1 declarations only shrink.

Counts the lines of every program's PDP-1 declarations (pdp1/*.toml and
programs/*/pdp1/*.toml), blank lines and comments aside, and compares the
count with the one recorded in pdp1/DECLARATIONS. More lines fail: hard RUNS
text is fixed in the text, and only the user raises the count. Fewer lines
fail too, until the commit lowers the recorded count, so each cut holds.

Usage: check_declarations.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "pdp1" / "DECLARATIONS"


def count() -> dict[Path, int]:
    files = sorted(ROOT.glob("pdp1/*.toml")) + sorted(ROOT.glob("programs/*/pdp1/*.toml"))
    return {f.relative_to(ROOT): sum(1 for line in f.read_text().splitlines()
                                     if line.strip() and not line.lstrip().startswith("#"))
            for f in files}


def main() -> int:
    lines = sum(count().values())
    recorded = int(re.search(r"^\d+", RECORD.read_text(), re.M).group())
    print(f"declarations: {lines} lines, {recorded} recorded")
    if lines > recorded:
        print(f"  {lines - recorded} more than recorded: fix the RUNS text instead; only the user raises the count")
        return 1
    if lines < recorded:
        print(f"  {recorded - lines} fewer: lower pdp1/DECLARATIONS to {lines} in this commit")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
