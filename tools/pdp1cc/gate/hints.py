"""G5: every hint earns its place.

A hint is a dialect annotation: a pdp1.h macro (JDA, BLOCK, BYNAME,
ENTRY_CELL, START, ...) or the `register` storage class. Each occurrence
outside comments is deleted in turn and the file compiled again. If the
Macro text does not change, the hint is decoration and the gate fails. A
compile error counts as a change: the hint was needed.

A header the files include with `#include "x.h"` is checked too: a hint
deleted there must change the output of some file that includes it."""
from __future__ import annotations

import re
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..cli import COMPILE_ERRORS, compile_file

HINT = re.compile(r"\b(?:PLACE|ARGS_DONE|CONSTANTS|VARIABLES)\s*\([^()]*\)\s*;"
                  r"|\b(?:ENTRY_CELL|AT)\s*\([^()]*\)"
                  r"|\b(?:JDA|BLOCK|BYNAME|INLINE|XCT|JSP|POOL|HOMED|RESERVE|START|SKIPS|register|home"
                  r"|SKIPNOT|SWAP)\b")
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
DIRECTIVE = re.compile(r"^[ \t]*#[^\n]*", re.M)
INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]+"([^"]+)"', re.M)


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


def without(h: Hint, includers: tuple[Path, ...] = ()) -> str | tuple[str, ...]:
    """The output with hint h deleted: of h's file, or for a header, of each
    file that includes it. Copies sit next to the originals so that their
    #include lines resolve the same way."""
    text = h.path.read_text()
    with tempfile.NamedTemporaryFile("w", suffix=h.path.suffix, dir=h.path.parent, prefix=".g5-") as f:
        f.write(text[:h.start] + text[h.end:])
        f.flush()
        if not includers:
            return output(Path(f.name))
        return tuple(including(c, h.path.name, Path(f.name)) for c in includers)


def including(c: Path, header: str, replacement: Path) -> str:
    """The output of c with its #include of header naming replacement instead."""
    text = INCLUDE.sub(lambda m: m.group(0).replace(m.group(1), str(replacement))
                       if m.group(1) == header else m.group(0), c.read_text())
    with tempfile.NamedTemporaryFile("w", suffix=".c", dir=c.parent, prefix=".g5-") as f:
        f.write(text)
        f.flush()
        return output(Path(f.name))


def headers_of(files: list[Path]) -> dict[Path, tuple[Path, ...]]:
    """Each quoted header the files include, with the files that include it."""
    out: dict[Path, list[Path]] = {}
    for f in files:
        for name in INCLUDE.findall(f.read_text()):
            out.setdefault((f.parent / name).resolve(), []).append(f)
    return {h: tuple(cs) for h, cs in out.items()}


def gate(files: list[Path]) -> int:
    headers = headers_of(files)
    files = files + list(headers)
    hints = [h for f in files for h in hints_in(f)]
    sources = [f for f in files if f not in headers]
    with ProcessPoolExecutor() as pool:
        base: dict[Path, str | tuple[str, ...]] = dict(zip(sources, pool.map(output, sources)))
        base |= {h: tuple(base[c] for c in cs) for h, cs in headers.items()}
        changed = list(pool.map(without, hints, [headers.get(h.path, ()) for h in hints]))
    bad = {h: "deleting it leaves the output unchanged"
           for h, out in zip(hints, changed) if out == base[h.path]}
    for f in files:
        mine = [h for h in hints if h.path == f]
        lines = f.read_text().count("\n") or 1
        flagged = [h for h in mine if h in bad]
        status = "ok" if not flagged else f"{len(flagged)} NOT EARNED"
        print(f"  {f.name:<16} {len(mine):>3} hints  {100 * len(mine) / lines:5.1f} per 100 lines  {status}")
        for h in flagged:
            print(f"    {f.name}:{h.line}: `{h.text}`: {bad[h]}")
    return 1 if bad else 0
