"""The PDP-1 declarations only shrink.

Counts the entries of every program's PDP-1 declarations (pdp1/*.toml and
programs/*/pdp1/*.toml), parsed as TOML: every scalar value and every list
element is one entry, and an empty table or list is one. A name added to an
existing line is an entry, as a new line is. The count is compared with the
one recorded in pdp1/DECLARATIONS. More entries fail: hard RUNS text is fixed
in the text, and only the user raises the count. Fewer fail too, until the
commit lowers the recorded count, so each cut holds.

Usage: check_declarations.py
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "pdp1" / "DECLARATIONS"


def entries(value) -> int:
    if isinstance(value, dict):
        return sum(entries(v) for v in value.values()) or 1
    if isinstance(value, list):
        return sum(entries(v) for v in value) or 1
    return 1


def count() -> dict[Path, int]:
    files = sorted(ROOT.glob("pdp1/*.toml")) + sorted(ROOT.glob("programs/*/pdp1/*.toml"))
    return {f.relative_to(ROOT): entries(tomllib.loads(f.read_text())) for f in files}


def main() -> int:
    total = sum(count().values())
    recorded = int(re.search(r"^\d+", RECORD.read_text(), re.M).group())
    print(f"declarations: {total} entries, {recorded} recorded")
    if total > recorded:
        print(f"  {total - recorded} more than recorded: fix the RUNS text instead; only the user raises the count")
        return 1
    if total < recorded:
        print(f"  {recorded - total} fewer: lower pdp1/DECLARATIONS to {total} in this commit")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
