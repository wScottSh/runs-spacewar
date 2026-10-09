"""Native reference build: g++ with pdp1.h gives `word` PDP-1 semantics, so
the dialect C runs on the host with the meaning the binary must have.

Two dialect storage facts have no spelling a header macro can give, so the
build binds them in a copy of each C file before compiling it:

- A JDA function's entry word is one cell, `pdp1_cell_<f>`. The call stores
  the AC argument there, the first parameter names it, and every
  ENTRY_CELL(f) object is a reference to it.
- A BYNAME parameter is the caller's word, fetched again on every read on the
  machine. It becomes `const word &`, so a write to that word between reads
  is seen, as `xct` sees it.

The rewrites are textual, so they fail closed: the preprocessed source
counts every BYNAME and ENTRY_CELL the front end sees, and a file where any
of them was not rewritten is an error, not a silently aliased build.

Nothing else in the C changes: operators keep their pdp1.h meaning."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .. import dialect, front, ir
from .simh import Inputs, Outcome

HEADER = Path(__file__).parent.parent / "include" / "pdp1.h"
DRIVER = Path(__file__).parent / "driver.cpp"
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
ARG = {"ac": "word::bits(ac)", "io": "word::bits(io)", "byname": "word::bits(byname)"}


def cell(fn: str) -> str:
    """The native name of a JDA function's entry word."""
    return f"pdp1_cell_{fn}"


@dataclass(frozen=True)
class Rewrite:
    """One storage fact: its spelling in the C, its g++ form, and the
    attribute the front end sees after preprocessing."""
    hint: str
    shape: str
    source: re.Pattern
    native: str
    attribute: re.Pattern


REWRITES = (
    Rewrite("BYNAME", "BYNAME word p", re.compile(r"\bBYNAME\s+word\s+(\w+)"),
            r"const word &\1", re.compile(r"\bpdp1_byname\b")),
    Rewrite("ENTRY_CELL", "ENTRY_CELL(f) word x;",
            re.compile(r"\bENTRY_CELL\((\w+)\)\s*word\s+(\w+)\s*;"),
            r"word &\2 = " + cell(r"\1") + ";", re.compile(r"\bpdp1_entry_cell\b")),
)


def entry_param(sig: ir.Signature) -> str | None:
    """The parameter a JDA call stores in the entry word."""
    if sig.conv != "jda":
        return None
    return next((p.name for p in sig.params if p.kind == "ac"), None)


class BindError(ValueError):
    pass


def rewrite_code(r: Rewrite, text: str) -> tuple[str, int]:
    """Apply r outside comments. Returns the text and the rewrite count."""
    done = 0

    def one(m: re.Match) -> str:
        nonlocal done
        if m.group("comment"):
            return m.group(0)
        done += 1
        return m.expand(r.native)
    return re.sub(rf"{r.source.pattern}|(?P<comment>{COMMENT.pattern})", one, text, flags=re.S), done


def bind(path: Path, defined: list[ir.Signature]) -> str:
    """defined: the functions this file defines."""
    text = path.read_text()
    pre = front.preprocess(path)
    for r in REWRITES:
        text, done = rewrite_code(r, text)
        want = len(r.attribute.findall(pre))
        if done != want:
            raise BindError(f"{path}: the reference build rewrote {done} of {want} {r.hint} "
                            f"uses; it binds only the shape `{r.shape}`")
    for sig in defined:
        param = entry_param(sig)
        if param is None:
            continue
        header = re.compile(rf"\b{sig.name}\s*\(([^)]*)\)((?:\s|/\*.*?\*/)*)\{{", re.S)

        def bind_param(m: re.Match) -> str:
            params = re.sub(rf"\bword\s+{param}\b", f"word pdp1_arg_{param}", m.group(1), count=1)
            return (f"{sig.name}({params}){m.group(2)}{{ word &{param} = "
                    f"({cell(sig.name)} = pdp1_arg_{param});")
        text, n = header.subn(bind_param, text)
        if n != 1:
            raise BindError(f"reference: found {n} definitions of {sig.name} to bind, want 1")
    return text


def units(c_files: list[Path]) -> dict[Path, ir.Unit]:
    return {f: dialect.lower_unit(front.parse(f)) for f in c_files}


def signatures(c_files: list[Path]) -> dict[str, ir.Signature]:
    return {name: s for u in units(c_files).values() for name, s in u.signatures.items()}


def call_expr(sig: ir.Signature) -> str:
    return f"{sig.name}({', '.join(ARG[p.kind] for p in sig.params)})"


def build(c_files: list[Path], sig: ir.Signature, out: Path, watch: list[str] = ()) -> Path:
    """c_files are included in order into one translation unit with the
    driver. watch holds C expressions of type word printed after each call."""
    out.parent.mkdir(parents=True, exist_ok=True)
    parsed = units(c_files)
    sigs = {name: s for u in parsed.values() for name, s in u.signatures.items()}
    src = out.parent / f"{out.name}-src"
    src.mkdir(exist_ok=True)
    cells = src / "cells.h"
    cells.write_text("".join(f"word {cell(s.name)};\n" for s in sigs.values() if entry_param(s)))
    bound = []
    for f, unit in parsed.items():
        defined = [fn.sig for fn in unit.items if isinstance(fn, ir.Function)]
        copy = src / f.name
        copy.write_text(f'#line 1 "{f.resolve()}"\n' + bind(f, defined))
        bound.append(copy)
    watch_expr = "".join(f' printf(" %06o", ({w}).v);' for w in watch)
    includes = [a for f in [cells, *bound] for a in ("-include", str(f))]
    subprocess.run(
        ["g++", "-std=c++14", "-O2", "-Wall", "-Wno-register", "-Wno-unused-label", "-Werror",
         "-include", str(HEADER), *includes,
         f"-DCALL={call_expr(sig)}", f"-DINLINE={sig.inline_count}",
         f"-DWATCH={watch_expr or ';'}", str(DRIVER), "-o", str(out),
         # Lifted code may name routines that are still unlifted Macro; the
         # reference run never reaches them.
         "-Wl,--unresolved-symbols=ignore-all"],
        check=True)
    return out


def run(binary: Path, calls: list[Inputs]) -> list[Outcome]:
    text = "".join(f"{c.ac:o} {c.io:o} {c.byname:o}\n" for c in calls)
    out = subprocess.run([str(binary)], input=text, capture_output=True, text=True, check=True).stdout
    rows = [[int(x, 8) for x in line.split()] for line in out.splitlines()]
    return [Outcome(r[0], r[1], r[2], tuple(r[3:])) for r in rows]
