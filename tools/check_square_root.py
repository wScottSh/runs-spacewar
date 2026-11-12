"""The square_root network file (runs/arithmetic/) against every input the
original routine was run on in SIMH (the observed sqt vectors:
all 65,536 inputs). Each input goes into the routine's entry word, and the
result is read from sq2."""
import json
import sys
from pathlib import Path

import runs

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "oracle/sqt-vectors.jsonl"


def main() -> int:
    m = runs.Machine(runs.program(runs.source()))
    total = differ = 0
    for line in VECTORS.read_text().splitlines():
        v = json.loads(line)
        m.state["square_root_call"]["entry"] = runs.W(int(v["in"], 8))
        m.run("square_root")
        got = m.state["square_root_call"]["root"]
        total += 1
        if got.v != int(v["ac"], 8):
            differ += 1
            if differ <= 5:
                print(f"  input {v['in']}: simh {v['ac']}, runs {got.v:06o}")
    print(f"square_root: {total} inputs, {total - differ} match, {differ} differ")
    return 1 if differ or total != 65536 else 0


if __name__ == "__main__":
    sys.exit(main())
