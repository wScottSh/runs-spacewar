"""Programs the dialect must refuse. Each tests/reject/*.c names the error it
expects in a `/* reject: <text> */` header; compiling it must fail with a
compile error whose message contains that text."""
from __future__ import annotations

import re
from pathlib import Path

from ..cli import COMPILE_ERRORS, compile_file

HEADER = re.compile(r"/\* reject: (.+?) \*/")


def gate(reject_dir: Path) -> int:
    failed = 0
    for path in sorted(reject_dir.glob("*.c")):
        m = HEADER.search(path.read_text())
        if not m:
            raise SystemExit(f"{path}: missing `/* reject: <expected error> */`")
        try:
            compile_file(path)
            verdict = "COMPILED (should be rejected)"
        except COMPILE_ERRORS as e:
            verdict = "rejected" if m.group(1) in str(e) else f"WRONG ERROR: {e}"
        failed += verdict != "rejected"
        print(f"  {path.name:<32} {verdict}")
    return 1 if failed else 0
