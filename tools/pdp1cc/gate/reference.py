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

Nothing else in the C changes: operators keep their pdp1.h meaning."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .. import dialect, front, ir
from .simh import Inputs, Outcome

HEADER = Path(__file__).parent.parent / "include" / "pdp1.h"
DRIVER = Path(__file__).parent / "driver.cpp"
ARG = {"ac": "word::bits(ac)", "io": "word::bits(io)", "byname": "word::bits(byname)"}
BYNAME_PARAM = re.compile(r"\bBYNAME\s+word\s+(\w+)")
ENTRY_CELL_DECL = re.compile(r"\bENTRY_CELL\((\w+)\)\s*word\s+(\w+)\s*;")


def cell(fn: str) -> str:
    """The native name of a JDA function's entry word."""
    return f"pdp1_cell_{fn}"


def entry_param(sig: ir.Signature) -> str | None:
    """The parameter a JDA call stores in the entry word."""
    if sig.conv != "jda":
        return None
    return next((p.name for p in sig.params if p.kind == "ac"), None)


def bind(text: str, defined: list[ir.Signature]) -> str:
    """defined: the functions this file defines."""
    text = BYNAME_PARAM.sub(r"const word &\1", text)
    text = ENTRY_CELL_DECL.sub(lambda m: f"word &{m.group(2)} = {cell(m.group(1))};", text)
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
            raise ValueError(f"reference: found {n} definitions of {sig.name} to bind, want 1")
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
        copy.write_text(f'#line 1 "{f.resolve()}"\n' + bind(f.read_text(), defined))
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
