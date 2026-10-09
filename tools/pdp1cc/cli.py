"""pdp1cc: lower | build."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import dialect, emit, front, layout


def compile_file(path: Path, label_prefix: str = "z", trace: bool = True) -> str:
    unit = dialect.lower_unit(front.parse(path))
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
    args = ap.parse_args(argv)

    if args.cmd == "lower":
        sys.stdout.write(compile_file(args.file, args.prefix, not args.no_trace))
        return 0
    from . import splice
    return splice.build(args.toml)


if __name__ == "__main__":
    sys.exit(main())
