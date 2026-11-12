"""Collisions as a phase of their own, against the walk as one chain.

The network files here replace object_walk.net: one fold runs every slot's
collisions, a second fold every slot's calc routine. The loader generates
the variant's source into a copy of runs/. The Evaluator then runs both
programs on check_frame's frames and counts the frames whose Records or
plotted points differ.

  PYTHONPATH=tools uv run -q python docs/prototypes/graph-format/object-walk/phases/compare.py [N]"""
from __future__ import annotations

import copy
import random
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import load  # noqa: E402
import check_frame  # noqa: E402
import check_spaceship as ship  # noqa: E402
import pdp1  # noqa: E402
import runs  # noqa: E402


def frame(m: runs.Machine, st: dict) -> dict:
    m.state.update(copy.deepcopy(st))
    m.state["display"] = []
    try:
        m.run("frame")
    except runs.Stop:
        m.state["halted"] = True
    return m.state


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    with tempfile.TemporaryDirectory() as d:
        variant = Path(d) / "runs"
        shutil.copytree(load.ROOT / "runs", variant)
        e = load.generate(load.load_all(HERE))
        for name, text in e.networks.items():
            path = variant / load.HOMES[name]
            old = path.read_text()
            s, t = load.region(old, name)
            path.write_text(old[:s] + text + old[t:])
        chain, phases = runs.program(load.ROOT / "runs"), runs.program(variant)
    a, b = runs.Machine(chain), runs.Machine(phases)
    outlines = ship.Outlines(a, pdp1.Binding(chain))
    rng = random.Random(0o1444)
    cases = [check_frame.a_frame(a, rng, outlines) for _ in range(n)]
    b.state.update(copy.deepcopy(a.state))      # the outlines the setup laid out
    differ = 0
    for k, (st, _) in enumerate(cases):
        x, y = frame(a, st), frame(b, st)
        apart = sorted(r for r in set(x) | set(y) if x.get(r) != y.get(r))
        if apart:
            differ += 1
            if differ <= 3:
                print(f"  frame {k}:", {r: [(f, x[r][f], y[r][f]) for f in x[r] if x[r][f] != y[r][f]]
                                        if isinstance(x.get(r), dict) else "differs" for r in apart})
    print(f"collisions as a phase against the chain: {n} frames, {differ} differ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
