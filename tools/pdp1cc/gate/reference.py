"""Native reference build: g++ with pdp1.h gives `word` PDP-1 semantics, so
the dialect C runs on the host with the meaning the binary must have."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .. import ir
from .simh import Inputs, Outcome

HEADER = Path(__file__).parent.parent / "include" / "pdp1.h"
DRIVER = Path(__file__).parent / "driver.cpp"
ARG = {"ac": "word::bits(ac)", "io": "word::bits(io)", "byname": "word::bits(byname)"}


def call_expr(sig: ir.Signature) -> str:
    return f"{sig.name}({', '.join(ARG[p.kind] for p in sig.params)})"


def build(c_files: list[Path], sig: ir.Signature, out: Path, watch: list[str] = ()) -> Path:
    """c_files are included in order into one translation unit with the driver."""
    out.parent.mkdir(parents=True, exist_ok=True)
    watch_expr = "".join(f' printf(" %06o", {w}.v);' for w in watch)
    includes = [a for f in c_files for a in ("-include", str(f.resolve()))]
    subprocess.run(
        ["g++", "-std=c++14", "-O2", "-Wall", "-Wno-register", "-Wno-unused-label", "-Werror",
         "-include", str(HEADER), *includes,
         f"-DCALL={call_expr(sig)}", f"-DINLINE={sig.inline_count}",
         f"-DWATCH={watch_expr or ';'}", str(DRIVER), "-o", str(out)],
        check=True)
    return out


def run(binary: Path, calls: list[Inputs]) -> list[Outcome]:
    text = "".join(f"{c.ac:o} {c.io:o} {c.byname:o}\n" for c in calls)
    out = subprocess.run([str(binary)], input=text, capture_output=True, text=True, check=True).stdout
    rows = [[int(x, 8) for x in line.split()] for line in out.splitlines()]
    return [Outcome(r[0], r[1], r[2], tuple(r[3:])) for r in rows]
