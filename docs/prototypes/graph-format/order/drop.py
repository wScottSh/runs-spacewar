"""Each fact of the call-form rule left out in turn: what the rule then picks.

  uv run -q python docs/prototypes/graph-format/order/drop.py

A fact earns its place when leaving it out picks an order whose image
differs from the original, at the address the fact decides."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arith  # noqa: E402
import graph  # noqa: E402
import rule  # noqa: E402

failed = 0
for fact in ("tests", "arrival"):
    rule.DROP = {fact}
    for name in arith.ROUTINES:
        r = arith.ROUTINES[name]
        g = arith.load(r)
        sigs = arith.signatures()
        graph.BOUNDARY = r.call
        verdicts = {rule.order(g, sigs, r, backward).verdict() for backward in (False, True)}
        print(f"without the {fact} fact, {name}: {' / '.join(sorted(verdicts))}")
        failed |= any("identical" not in v for v in verdicts)
print("some routine's image differs without a fact" if failed else "every image is identical without either fact")
