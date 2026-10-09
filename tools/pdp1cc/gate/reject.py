"""Programs the toolchain must refuse. Each tests/reject/*.c names the error it
expects in a header. `/* reject: <text> */`: compiling it must fail with a
compile error whose message contains that text. `/* reject-reference: <text> */`:
a program the dialect accepts but the native reference build cannot bind;
binding it must fail with that text instead of building a wrong reference."""
from __future__ import annotations

import re
from pathlib import Path

from .. import ir
from ..cli import COMPILE_ERRORS, compile_file
from . import reference

HEADER = re.compile(r"/\* (reject|reject-reference): (.+?) \*/")


def refuse(kind: str, path: Path) -> None:
    compile_file(path)
    if kind == "reject":
        return
    unit = reference.units([path])[path]
    reference.bind(path, [f.sig for f in unit.items if isinstance(f, ir.Function)])


def gate(reject_dir: Path) -> int:
    failed = 0
    for path in sorted(reject_dir.glob("*.c")):
        m = HEADER.search(path.read_text())
        if not m:
            raise SystemExit(f"{path}: missing `/* reject: <expected error> */` "
                             "or `/* reject-reference: <expected error> */`")
        kind, want = m.groups()
        errors = COMPILE_ERRORS if kind == "reject" else (reference.BindError,)
        try:
            refuse(kind, path)
            verdict = "ACCEPTED (should be rejected)"
        except errors as e:
            verdict = "rejected" if want in str(e) else f"WRONG ERROR: {e}"
        failed += verdict != "rejected"
        print(f"  {path.name:<32} {verdict}")
    return 1 if failed else 0
