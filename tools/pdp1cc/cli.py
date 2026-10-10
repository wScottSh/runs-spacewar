"""pdp1cc: lower | build."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import dialect, emit, front, inline, ir, layout, select

COMPILE_ERRORS = (dialect.DialectError, select.SelectError, layout.LayoutError, inline.ArgsError)


def compile_file(path: Path, label_prefix: str = "z", trace: bool = True) -> str:
    return emit.emit(lay_out(front.parse(path), label_prefix), trace)


def compile_ast(ast, label_prefix: str = "z", trace: bool = True) -> str:
    return emit.emit(lay_out(ast, label_prefix), trace)


def compile_regions(path: Path, label_prefix: str) -> list[list[str]]:
    """The Macro lines of each region the file's REGION_BREAK()s separate."""
    return emit.regions(lay_out(front.parse(path), label_prefix))


def lay_out(ast, label_prefix: str) -> list[ir.Emitted]:
    return layout.place(dialect.lower_unit(ast, label_prefix), label_prefix)


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
    ga.add_argument("--reject", type=Path, default=Path("tests/reject"))
    ga.add_argument("--lift", type=Path, default=Path("lift.toml"))
    ga.add_argument("--simh", type=Path, default=Path("build/pdp1"))
    ga.add_argument("--macro1", type=Path, default=Path("build/macro1"))
    ga.add_argument("--work", type=Path, default=Path("build/gate"))
    args = ap.parse_args(argv)

    if args.cmd == "lower":
        try:
            sys.stdout.write(compile_file(args.file, args.prefix, not args.no_trace))
        except COMPILE_ERRORS as e:
            print(f"{args.file}: error: {e}", file=sys.stderr)
            return 1
        return 0
    from . import splice
    if args.cmd == "build":
        return splice.build(args.toml)
    from .gate import corpus, hints, predict, reject
    _, regions = splice.load(args.lift.resolve())
    print("G2 corpus: SIMH against the native reference build")
    failed = corpus.gate(args.corpus, [r.c for r in regions], args.simh.resolve(),
                         args.macro1.resolve(), args.work.resolve())
    print("rejects: programs the dialect must refuse")
    failed |= reject.gate(args.reject)
    lifted = [r.c for r in regions]
    corpus_files = sorted(args.corpus.glob("*.c"))
    print("G5 hints: deleting any hint must change the output; a SYM must pin a symbol "
          "unlifted text names")
    failed |= hints.gate(lifted + corpus_files, splice.unlifted_text(args.lift.resolve()))
    print("G6 prediction edits: each edit changes exactly the words the rules predict")
    failed |= predict.gate(lifted + corpus_files)
    print("gate " + ("FAILED" if failed else "ok"))
    return failed


if __name__ == "__main__":
    sys.exit(main())
