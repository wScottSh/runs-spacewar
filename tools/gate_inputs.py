"""Which changed files the checks read, so check_all.sh runs only when one did.

Changed: every file that differs from where this branch meets origin/main,
committed or not, untracked ones included. Read by the checks: the game's
data (the RUNS text, the declarations, the original source and its lift,
the oracle vectors, the second program) and every file under tools/ that
check_all.sh reaches by name, directly or through a file it reaches. A new
script that nothing names is not read, and neither is anything in docs/.

Prints one changed input per line; prints nothing when no check reads any
change. `--spec DIR` prints the spec's changed files instead, for its
example check.

Usage: gate_inputs.py [--spec DIR]"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DATA = ("runs/", "pdp1/", "programs/", "source/", "lift/", "oracle/", "ref/")
PROJECT = {"pyproject.toml", "uv.lock", "lift.toml"}


def git(root: Path, *args: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
    return out.stdout.split("\n")[:-1]


def changed(root: Path) -> set[str]:
    base = git(root, "merge-base", "HEAD", "origin/main")[0]
    return set(git(root, "diff", "--name-only", base)) | \
        set(git(root, "ls-files", "--others", "--exclude-standard"))


def reached_tools(root: Path) -> set[str]:
    """tools/ files named by check_all.sh, and by those, to a fixed point."""
    tools = [p for p in (root / "tools").rglob("*")
             if p.is_file() and "__pycache__" not in p.parts]
    reached = {root / "tools/check_all.sh"}
    text = (root / "tools/check_all.sh").read_text()
    while True:
        new = {p for p in tools if p not in reached and any(
            re.search(rf"\b{re.escape(n)}\b", text) for n in {p.name, p.stem, p.parent.name} - {"tools"})}
        if not new:
            return {str(p.relative_to(root)) for p in reached}
        reached |= new
        text += "".join(p.read_text(errors="ignore") for p in new)


def main() -> int:
    if sys.argv[1:2] == ["--spec"]:
        inputs = changed(Path(sys.argv[2]))
    else:
        root = Path(__file__).resolve().parent.parent
        tools = reached_tools(root)
        inputs = {f for f in changed(root) if f.startswith(DATA) or f in PROJECT or f in tools}
    for f in sorted(inputs):
        print(f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
