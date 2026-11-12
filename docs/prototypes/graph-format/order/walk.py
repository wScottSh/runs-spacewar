"""The order rule on the object walk (../object-walk/): the image stays the
original's with every network file's in, inout and out lines reversed
(active_object's `inout seen` and `inout table` swapped among them), and
with names breaking ties backward. Last, a planted defect: the rule without
its guard fact must give an image that differs.

  uv run -q python docs/prototypes/graph-format/order/walk.py"""
from __future__ import annotations

import importlib.util
import itertools
import re
import shutil
import sys
import tempfile
from pathlib import Path

WALK = Path(__file__).resolve().parents[1] / "object-walk"
spec = importlib.util.spec_from_file_location("walk_load", WALK / "load.py")
walk = importlib.util.module_from_spec(spec)
sys.modules["walk_load"] = walk
spec.loader.exec_module(walk)


def reversed_ports(text: str) -> str:
    lines = text.splitlines(keepends=True)
    at = [i for i, line in enumerate(lines) if re.match(r"\s+(in|out|inout) \w+:", line)]
    for i, line in zip(at, reversed([lines[i] for i in at])):
        lines[i] = line
    return "".join(lines)


failed = 0
for ports_reversed, backward, tests_last in [(p, b, True) for p in (False, True) for b in (False, True)] + [(False, True, False)]:
    walk.NAMES_BACKWARD, walk.TESTS_LAST = backward, tests_last
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        over = tmp / "nets"
        over.mkdir()
        for f in WALK.glob("*.net"):
            (over / f.name).write_text(reversed_ports(f.read_text()) if ports_reversed else f.read_text())
        shutil.copytree(walk.ROOT / "runs", tmp / "runs")
        e = walk.generate(walk.load_all(over))
        for name, text in e.networks.items():
            path = tmp / "runs" / walk.HOMES[name]
            old = path.read_text()
            s, t = walk.region(old, name)
            path.write_text(old[:s] + text + old[t:])
        code = walk.runsc.build(walk.runs.program(tmp / "runs"), tmp / "out")
        said = walk.runsc.build.said.strip().splitlines()[-1].strip()
        said = next((x.strip() for x in walk.runsc.build.said.splitlines() if 'first difference' in x), said)
        failed |= code if tests_last else not code
        print(f"{'' if tests_last else 'planted defect, the guard fact left out: '}"
              f"ports {'reversed' if ports_reversed else 'as written'}, names {'backward' if backward else 'forward'}: "
              f"active_object {', '.join(e.orders['active_object'])}; {said}")
sys.exit(failed)
