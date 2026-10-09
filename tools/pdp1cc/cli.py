"""pdp1cc: lower | build."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import dialect, emit, front, layout


def compile_file(path: Path, label_prefix: str = "z", trace: bool = True) -> str:
    unit = dialect.lower_unit(front.parse(path), label_prefix)
    return emit.emit(layout.place(unit, label_prefix), trace)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pdp1cc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lo = sub.add_parser("lower", help="compile one C file to Macro text")
    lo.add_argument("file", type=Path)
    lo.add_argument("--prefix", default="z", help="generated-label prefix")
    lo.add_argument("--no-trace", action="store_true")
    bu = sub.add_parser("build", help="splice lifted regions, assemble, compare sha256")
    bu.add_argument("toml", type=Path, nargs="?", default=Path("lift.toml"))
    ga = sub.add_parser("gate", help="G2: run the corpus in SIMH against the reference build")
    ga.add_argument("--corpus", type=Path, default=Path("tests/corpus"))
    ga.add_argument("--lift", type=Path, default=Path("lift.toml"))
    ga.add_argument("--simh", type=Path, default=Path("build/pdp1"))
    ga.add_argument("--macro1", type=Path, default=Path("build/macro1"))
    ga.add_argument("--work", type=Path, default=Path("build/gate"))
    args = ap.parse_args(argv)

    if args.cmd == "lower":
        sys.stdout.write(compile_file(args.file, args.prefix, not args.no_trace))
        return 0
    from . import splice
    if args.cmd == "build":
        return splice.build(args.toml)
    from .gate import corpus
    _, regions = splice.load(args.lift.resolve())
    return corpus.gate(args.corpus, [r.c for r in regions], args.simh.resolve(),
                       args.macro1.resolve(), args.work.resolve())


if __name__ == "__main__":
    sys.exit(main())
