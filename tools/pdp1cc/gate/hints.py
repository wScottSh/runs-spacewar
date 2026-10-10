"""G5: every hint earns its place.

A hint is a dialect annotation: a pdp1.h macro (SYM, JDA, BLOCK, BYNAME,
ENTRY_CELL, ...) or the `register` storage class. Each occurrence outside
comments is deleted in turn and the file compiled again. If the Macro text
does not change, the hint is decoration and the gate fails. A compile error
counts as a change: the hint was needed.

SYM is the exception: deleting it always renames a label, so that test
cannot catch a stale one. A SYM earns its place while unlifted source text
still names the symbol it pins, or while another lifted file pins the same
symbol: the two files name one object, and without the pin each would give
it a symbol of its own. A SYM in a header is shared the same way when two of
the files that include it use the name it declares. The gate fails when
none of these holds.

A header the files include with `#include "x.h"` is checked too: a hint
deleted there must change the output of some file that includes it."""
from __future__ import annotations

import re
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..cli import COMPILE_ERRORS, compile_file

SYM = re.compile(r'SYM\s*\(\s*"(\w+)"\s*\)')
HINT = re.compile(r"\b(?:PLACE|ARGS_DONE|CONSTANTS|VARIABLES)\s*\([^()]*\)\s*;"
                  r"|\b(?:SYM|ENTRY_CELL|AT)\s*\([^()]*\)"
                  r"|\b(?:JDA|BLOCK|BYNAME|INLINE|XCT|JSP|POOL|HOMED|RESERVE|register|home"
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


def pinned(h: Hint) -> str | None:
    m = SYM.fullmatch(h.text)
    return m.group(1) if m else None


DECLARED = re.compile(r"(\w+)\s*(?:\[[^]]*\])?\s*SYM\s*\(")


def stale(h: Hint, unlifted: str, pins: dict[Path, set[str]],
          includers: tuple[Path, ...] = ()) -> bool:
    """unlifted: the source text no region covers, comments removed. pins:
    the symbols each file's SYMs pin. includers: the files that include
    h's header."""
    shared = any(pinned(h) in syms for f, syms in pins.items() if f != h.path)
    line = h.path.read_text().splitlines()[h.line - 1]
    if (m := DECLARED.search(line)) is not None:
        users = [f for f in includers if re.search(rf"\b{m.group(1)}\b", f.read_text())]
        shared |= len(users) >= 2
    return not shared and not re.search(rf"(?<!\w){pinned(h)}(?!\w)", unlifted)


def gate(files: list[Path], unlifted: str) -> int:
    headers = headers_of(files)
    files = files + list(headers)
    hints = [h for f in files for h in hints_in(f)]
    syms = [h for h in hints if pinned(h)]
    pins: dict[Path, set[str]] = {}
    for h in syms:
        pins.setdefault(h.path, set()).add(pinned(h))
    others = [h for h in hints if not pinned(h)]
    sources = [f for f in files if f not in headers]
    with ProcessPoolExecutor() as pool:
        base: dict[Path, str | tuple[str, ...]] = dict(zip(sources, pool.map(output, sources)))
        base |= {h: tuple(base[c] for c in cs) for h, cs in headers.items()}
        changed = list(pool.map(without, others, [headers.get(h.path, ()) for h in others]))
    bad = {h: "deleting it leaves the output unchanged"
           for h, out in zip(others, changed) if out == base[h.path]}
    bad |= {h: "no unlifted source text names the symbol it pins"
            for h in syms if stale(h, unlifted, pins, headers.get(h.path, ()))}
    for f in files:
        mine = [h for h in hints if h.path == f]
        lines = f.read_text().count("\n") or 1
        flagged = [h for h in mine if h in bad]
        status = "ok" if not flagged else f"{len(flagged)} NOT EARNED"
        print(f"  {f.name:<16} {len(mine):>3} hints  {100 * len(mine) / lines:5.1f} per 100 lines  {status}")
        for h in flagged:
            print(f"    {f.name}:{h.line}: `{h.text}`: {bad[h]}")
    return 1 if bad else 0
