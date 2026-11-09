"""The RUNS Network as data for the viewer (viewer/): each Record a place
with its fields, each Processor a transition with the Records it reads
and writes. Every value comes from the RUNS text, through the evaluator's
loader and checker.

Usage: runs_net.py [RUNS dir] > net.json (default: runs/)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import runs

DECLARATION = re.compile(r"^(?:(game|interface|presentation) )?(record|stream|processor|network) (\w+)")
FIELD = re.compile(r"^  (\w+): (\w+)(?: = ?(.*))?$")


def scan(root: Path) -> tuple[dict[str, str], dict[str, list[dict]]]:
    """Each declaration's file, and each Record's fields as the text
    writes them."""
    home, fields = {}, {}
    for path in sorted(root.glob("*.runs")) + sorted(root.glob("*.runs-prim")):
        current = None
        for line in path.read_text().splitlines():
            if m := DECLARATION.match(line):
                home[m[3]] = path.stem
                current = m[3] if m[2] in ("record", "stream") else None
                if current:
                    fields[current] = []
            elif current and (f := FIELD.match(line.split("#")[0].rstrip())):
                init = f[3]
                fields[current].append({"name": f[1], "type": f[2],
                                        "init": "one a slot" if init == "" else init})
            elif line and not line.startswith(" "):
                current = None
    return home, fields


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else runs.source()
    # The kind rules are left out so the drawing can show where they break.
    prog = runs.check(runs.load(sorted(root.glob("*.runs")) + sorted(root.glob("*.runs-prim"))), sides=False)
    home, fields = scan(root)
    kinds = {n: r.side for n, r in prog.records.items()}
    shown = runs.presentation_routines(prog) if any(kinds.values()) else set()
    out = {
        "title": root.resolve().parent.name if root.name == "runs" else root.name,
        "records": [{"name": n, "kind": r.side, "file": home.get(n), "count": r.count, "stream": r.stream,
                     "fields": fields.get(n, [])} for n, r in prog.records.items()],
        "processors": [],
    }
    for n, r in prog.routines.items():
        if r.kind != "processor":
            continue
        touched = {kinds.get(x) for x in r.reads | r.writes}
        out["processors"].append({
            "name": n, "file": home.get(n), "params": r.params,
            "side": ("presentation" if n in shown else "game") if any(kinds.values()) else None,
            "mixed": {"game", "presentation"} <= touched,
            "reads": sorted(r.reads - r.writes), "writes": sorted(r.writes)})
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
