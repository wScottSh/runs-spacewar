"""C source -> pycparser AST: gcc -E with the dialect header, then the GNU parser
(pycparserext keeps __attribute__ in every position the dialect uses)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from pycparser import c_ast
from pycparserext.ext_c_parser import GnuCParser

HEADER = Path(__file__).parent / "include" / "pdp1.h"


def preprocess(path: Path) -> str:
    out = subprocess.run(
        ["gcc", "-E", "-D__PDP1CC__", "-include", str(HEADER), str(path)],
        check=True, capture_output=True, text=True,
    )
    return out.stdout


def parse(path: Path) -> c_ast.FileAST:
    return GnuCParser().parse(preprocess(path), filename=str(path))
