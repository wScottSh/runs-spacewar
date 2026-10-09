"""Native reference build: g++ with pdp1.h gives `word` PDP-1 semantics, so
the dialect C runs on the host with the meaning the binary must have."""
from __future__ import annotations

import subprocess
from pathlib import Path

HEADER = Path(__file__).parent.parent / "include" / "pdp1.h"
DRIVER = Path(__file__).parent / "driver.cpp"


def build(c_file: Path, entry: str, out: Path, watch: list[str] = ()) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    watch_expr = "".join(f' printf(" %06o", {w}.v);' for w in watch)
    subprocess.run(
        ["g++", "-std=c++14", "-O2", "-Wall", "-Wno-register", "-Werror",
         "-include", str(HEADER), "-include", str(c_file.resolve()),
         f"-DENTRY={entry}", f"-DWATCH={watch_expr or ';'}",
         str(DRIVER), "-o", str(out)],
        check=True)
    return out


def run(binary: Path, inputs: list[int]) -> list[tuple[int, ...]]:
    text = "".join(f"{v:o}\n" for v in inputs)
    out = subprocess.run([str(binary)], input=text, capture_output=True, text=True, check=True).stdout
    return [tuple(int(x, 8) for x in line.split()) for line in out.splitlines()]
