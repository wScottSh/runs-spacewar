"""A network file states no order, so a transition's name decides nothing in
the image. Each network file of the RUNS source has its transitions renamed
so their name order reverses, and then shuffled by a seeded draw; each must
compile to the original image.

Usage: [file.net ...] (the network files to rename; default every one).
Run from the repository root:
  uv run python tools/check_names.py"""
from __future__ import annotations

import random
import re
import shutil
import sys
import tempfile
from pathlib import Path

import graph
import runs
import runsc


def transitions(path: Path) -> list[str]:
    """The transitions a network file names, the stop it halts at included."""
    g = graph.parse(path)
    return list(g.transitions) + ([g.halt] if g.halt else [])


def renamed(path: Path, order: list[str]) -> str:
    """path's source with transition order[k] named t<k>_<old name>, so the
    names sort in order's order."""
    names = transitions(path)
    new = {t: f"t{k:02d}_{t}" for k, t in enumerate(order)}
    assert sorted(new) == sorted(names)
    out, section = [], None
    for line in path.read_text().splitlines():
        code, hash_, note = line.partition("#")
        if code and not code.startswith(" "):
            section = code.strip()
        if section == "transitions" and code.startswith(" ") and ":" in code:
            t, colon, rest = code.partition(":")
            code = t.replace(t.strip(), new[t.strip()]) + colon + rest
        elif section == "arcs" and code.strip():
            code = re.sub(r"(?<![\w.\]])(\w+)(?=\.|\s|$)", lambda m: new.get(m[1], m[1]), code)
        out.append(code + hash_ + note)
    return "\n".join(out) + "\n"


def identical(root: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as out:
        try:
            code = runsc.build(runsc.pdp1_program(root), Path(out))
        except (runsc.BindError, runs.RunsError) as e:
            return False, f"refused: {e}"
    said = runsc.build.said
    lines = [s.strip() for s in said.splitlines() if s.strip()]
    return code == 0, next((s for s in lines if "first difference" in s), lines[-1] if lines else "")


def main() -> int:
    source = runs.source()
    files = [Path(a).resolve() for a in sys.argv[1:]] or sorted(source.rglob("*.net"))
    failed = 0
    for path in files:
        names = transitions(path)
        for how, order in (("reversed", sorted(names, reverse=True)),
                           ("shuffled", random.Random(path.name).sample(names, len(names)))):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / source.name
                shutil.copytree(source, root)
                target = root / path.relative_to(source)
                target.write_text(renamed(path, order))
                ok, why = identical(root)
            print(f"  {'ok' if ok else 'DIFFERS'}: {path.relative_to(source)} {how}{'' if ok else ': ' + why}")
            failed += not ok
    print(f"check_names: {2 * len(files) - failed} of {2 * len(files)} renamings identical to the original")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
