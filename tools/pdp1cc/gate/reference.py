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
INPUT = {ir.ParamKind.AC: "ac", ir.ParamKind.IO: "io", ir.ParamKind.BYNAME: "byname",
         ir.ParamKind.INLINE: "byname"}


def native_param(p: ir.Param) -> str:
    if p.kind is ir.ParamKind.BYNAME:
        return "const word &"
    if p.pointer:
        return "const word *" if p.kind is ir.ParamKind.INLINE else "word *"
    return "word"


def native_arg(p: ir.Param) -> str:
    """The driver's argument for p: a word, or the C object at the address
    the caller passes (pointers name addresses on the machine)."""
    value = INPUT[p.kind]
    return f"pdp1_pointer({value})" if p.pointer else f"word::bits({value})"


@dataclass(frozen=True)
class Placement:
    """Where the machine holds a C object: native expression, words, address."""
    native: str
    words: int
    address: int
    function: bool = False


def placements(unit: ir.Unit, symbols: dict[str, int]) -> list[Placement]:
    """The objects and functions of a unit whose Macro symbols the assembled
    listing places. unit must be lowered with the assembly's label prefix."""
    out = []
    for name, storage in unit.objects.items():
        if isinstance(storage, (ir.Placed, ir.Pool)) and storage.sym in symbols:
            out.append(Placement(f"&{name}", unit.words(name), symbols[storage.sym]))
    out += [Placement(f"&{name}", 1, symbols[s.sym], function=True)
            for name, s in unit.signatures.items() if s.sym in symbols]
    return out


def symbol_table(placed: list[Placement]) -> str:
    rows = [f"    {{{'reinterpret_cast<const void *>(' + p.native + ')' if p.function else p.native},"
            f" {p.words}u, 0{p.address:o}u}},\n" for p in placed]
    return ("const pdp1_symbol pdp1_symbols[] = {\n" + "".join(rows)
            + "    {nullptr, 0u, 0u},\n};\n"
            + f"const unsigned pdp1_symbol_count = {len(placed)}u;\n")


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
            re.compile(r"\bENTRY_CELL\((\w+)\)\s*word\s*(\*?)\s*(\w+)\s*;"),
            r"word \2&\3 = " + cell(r"\1") + ";", re.compile(r"\bpdp1_entry_cell\b")),
)


def entry(sig: ir.Signature) -> ir.Param | None:
    """The parameter a JDA call stores in the entry word."""
    if sig.conv is not ir.Conv.JDA:
        return None
    return next((p for p in sig.params if p.kind is ir.ParamKind.AC), None)


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
        p = entry(sig)
        if p is None:
            continue
        param, star = p.name, "*" if p.pointer else ""
        header = re.compile(rf"\b{sig.name}\s*\(([^)]*)\)((?:\s|/\*.*?\*/)*)\{{", re.S)

        def bind_param(m: re.Match) -> str:
            params = re.sub(rf"\bword\s*{re.escape(star)}\s*{param}\b", f"word {star}pdp1_arg_{param}",
                            m.group(1), count=1)
            return (f"{sig.name}({params}){m.group(2)}{{ word {star}&{param} = "
                    f"({cell(sig.name)} = pdp1_arg_{param});")
        text, n = header.subn(bind_param, text)
        if n != 1:
            raise BindError(f"reference: found {n} definitions of {sig.name} to bind, want 1")
    return text


def units(c_files: list[Path]) -> dict[Path, ir.Unit]:
    return {f: dialect.lower_unit(front.parse(f)) for f in c_files}


def stub(sig: ir.Signature) -> str:
    """A definition for a function the linked files declare but none defines:
    an unlifted routine. The reference run must never reach it."""
    params = ", ".join(native_param(p) for p in sig.params)
    return f"{sig.returns} {sig.name}({params}) {{ std::abort(); }}\n"


def call_expr(sig: ir.Signature, name: str | None = None) -> str:
    return f"{name or sig.name}({', '.join(native_arg(p) for p in sig.params)})"


def build(c_files: list[Path], sig: ir.Signature, out: Path, watch: list[str] = (),
          placed: list[Placement] = (), scratch: str = "", native: str | None = None) -> Path:
    """c_files are included in order into one translation unit with the
    driver. watch holds C expressions of a word or pointer type printed after
    each call. placed says where the machine holds C objects, for instruction
    words and pointers. scratch is extra C++ (words the caller sets up)
    included after the files. native names a function to call in place of
    sig's: the program's own statement of what sig computes, for an entry
    the native build cannot run (one that jumps into generated code)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    parsed = units(c_files)
    sigs = {name: s for u in parsed.values() for name, s in u.signatures.items()}
    src = out.parent / f"{out.name}-src"
    src.mkdir(exist_ok=True)
    cells = src / "cells.h"
    cells.write_text("".join(f"word {'*' if entry(s).pointer else ''}{cell(s.name)};\n"
                             for s in sigs.values() if entry(s)))
    bound, defined = [], set()
    for f, unit in parsed.items():
        mine = [fn.sig for fn in unit.items if isinstance(fn, ir.Function)]
        defined |= {s.name for s in mine} | set(unit.inlines or {})
        copy = src / f.name
        copy.write_text(f'#line 1 "{f.resolve()}"\n' + bind(f, mine))
        bound.append(copy)
    stubs = src / "stubs.h"
    stubs.write_text("".join(stub(s) for name, s in sigs.items() if name not in defined)
                     + scratch + symbol_table(list(placed)))
    watch_expr = "".join(f' printf(" %06o", pdp1_value({w}));' for w in watch)
    includes = [a for f in [cells, *bound, stubs] for a in ("-include", str(f))]
    subprocess.run(
        ["g++", "-std=c++14", "-O2", "-Wall", "-Wno-register", "-Wno-unused-label", "-Wno-array-bounds",
         "-Werror",
         "-include", str(HEADER), *includes,
         f"-DCALL={call_expr(sig, native)}", f"-DINLINE_WORDS={sig.inline_count}",
         f"-DWATCH={watch_expr or ';'}", str(DRIVER), "-o", str(out)],
        check=True)
    return out


def run(binary: Path, calls: list[Inputs]) -> list[Outcome]:
    text = "".join(f"{c.ac:o} {c.io:o} {c.byname:o} {c.sense:o}\n" for c in calls)
    out = subprocess.run([str(binary)], input=text, capture_output=True, text=True, check=True).stdout
    outcomes = []
    for line in out.splitlines():
        words, _, plots = line.partition(";")
        r = [int(x, 8) for x in words.split()]
        p = [int(x, 8) for x in plots.split()]
        outcomes.append(Outcome(r[0], r[1], r[2], tuple(r[3:]),
                                tuple(tuple(p[k:k + 3]) for k in range(0, len(p), 3))))
    return outcomes
