"""G5: every hint earns its place.

A hint is a dialect annotation: a pdp1.h macro (SYM, JDA, BLOCK, BYNAME,
ENTRY_CELL, ...) or the `register` storage class. Each occurrence outside
comments is deleted in turn and the file compiled again. If the Macro text
does not change, the hint is decoration and the gate fails. A compile error
counts as a change: the hint was needed."""
from __future__ import annotations

import re
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..cli import COMPILE_ERRORS, compile_file

HINT = re.compile(r"\b(?:SYM|ENTRY_CELL|AT|RESERVE)\s*\([^()]*\)|\b(?:JDA|BLOCK|BYNAME|XCT|JSP|register)\b")
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
DIRECTIVE = re.compile(r"^[ \t]*#[^\n]*", re.M)


@dataclass(frozen=True)
class Hint:
    path: Path
    start: int
    end: int
    line: int
    text: str


def blank(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def hints_in(path: Path) -> list[Hint]:
    text = path.read_text()
    code = DIRECTIVE.sub(blank, COMMENT.sub(blank, text))
    return [Hint(path, m.start(), m.end(), text.count("\n", 0, m.start()) + 1, m.group(0))
            for m in HINT.finditer(code)]


def output(path: Path) -> str:
    try:
        return compile_file(path, trace=False)
    except COMPILE_ERRORS as e:
        return f"error: {e}"


def without(h: Hint) -> str:
    """The output with hint h deleted. The copy sits next to the original so
    that its #include lines resolve the same way."""
    text = h.path.read_text()
    with tempfile.NamedTemporaryFile("w", suffix=".c", dir=h.path.parent, prefix=".g5-") as f:
        f.write(text[:h.start] + text[h.end:])
        f.flush()
        return output(Path(f.name))


def gate(files: list[Path]) -> int:
    hints = [h for f in files for h in hints_in(f)]
    with ProcessPoolExecutor() as pool:
        base = dict(zip(files, pool.map(output, files)))
        changed = list(pool.map(without, hints))
    decorative = [h for h, out in zip(hints, changed) if out == base[h.path]]
    for f in files:
        mine = [h for h in hints if h.path == f]
        lines = f.read_text().count("\n") or 1
        bad = [h for h in decorative if h.path == f]
        status = "ok" if not bad else f"{len(bad)} DECORATIVE"
        print(f"  {f.name:<16} {len(mine):>3} hints  {100 * len(mine) / lines:5.1f} per 100 lines  {status}")
        for h in bad:
            print(f"    {f.name}:{h.line}: deleting `{h.text}` leaves the output unchanged")
    return 1 if decorative else 0
