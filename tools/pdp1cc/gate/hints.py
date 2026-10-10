"""G5: every hint earns its place.

A hint is a dialect annotation: a pdp1.h macro (SYM, JDA, BLOCK, BYNAME,
ENTRY_CELL, ...) or the `register` storage class. Each occurrence outside
comments is deleted in turn and the file compiled again. If the Macro text
does not change, the hint is decoration and the gate fails. A compile error
counts as a change: the hint was needed.

SYM is the exception: deleting it always renames a label, so that test
cannot catch a stale one. A SYM earns its place while unlifted source text
still names the symbol it pins; the gate fails when nothing unlifted does."""
from __future__ import annotations

import re
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..cli import COMPILE_ERRORS, compile_file

SYM = re.compile(r'SYM\s*\(\s*"(\w+)"\s*\)')
HINT = re.compile(r"\b(?:PLACE|ARGS_DONE)\s*\([^()]*\)\s*;"
                  r"|\b(?:SYM|ENTRY_CELL|AT)\s*\([^()]*\)"
                  r"|\b(?:JDA|BLOCK|BYNAME|INLINE|XCT|JSP|POOL|HOMED|RESERVE|register|home)\b")
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


def pinned(h: Hint) -> str | None:
    m = SYM.fullmatch(h.text)
    return m.group(1) if m else None


def stale(h: Hint, unlifted: str) -> bool:
    """unlifted: the source text no region covers, comments removed."""
    return not re.search(rf"(?<!\w){pinned(h)}(?!\w)", unlifted)


def gate(files: list[Path], unlifted: str) -> int:
    hints = [h for f in files for h in hints_in(f)]
    syms = [h for h in hints if pinned(h)]
    others = [h for h in hints if not pinned(h)]
    with ProcessPoolExecutor() as pool:
        base = dict(zip(files, pool.map(output, files)))
        changed = list(pool.map(without, others))
    bad = {h: "deleting it leaves the output unchanged"
           for h, out in zip(others, changed) if out == base[h.path]}
    bad |= {h: "no unlifted source text names the symbol it pins"
            for h in syms if stale(h, unlifted)}
    for f in files:
        mine = [h for h in hints if h.path == f]
        lines = f.read_text().count("\n") or 1
        flagged = [h for h in mine if h in bad]
        status = "ok" if not flagged else f"{len(flagged)} NOT EARNED"
        print(f"  {f.name:<16} {len(mine):>3} hints  {100 * len(mine) / lines:5.1f} per 100 lines  {status}")
        for h in flagged:
            print(f"    {f.name}:{h.line}: `{h.text}`: {bad[h]}")
    return 1 if bad else 0
