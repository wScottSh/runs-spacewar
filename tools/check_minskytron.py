"""The Minskytron's RUNS against the original, point for point.

For each test word, the evaluator (runs.py) fires the start Network once,
with the test word switches set, then the pass Network again and again, as
the machine does. SIMH boots programs/minskytron/source/minskytron.rim as
the machine reads a tape, with the same test word, and runs it; every dpy
it executes is a point (AC, IO). The two point streams must be equal, point
for point, over every pass.

Usage: check_minskytron.py [--passes N] [--runs DIR] [TESTWORD ...] (octal)."""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import census_generated_code as census
import runs

ro = census.ro
ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "programs/minskytron"
TAPE = PROGRAM / "source/minskytron.rim"
CHUNK = 60000                   # instructions per history read; SIMH keeps 65536


def evaluator(prog: runs.Program, test_word: int, passes: int) -> list[tuple[int, int]]:
    m = runs.Machine(prog)
    m.state["console"]["test_word"] = runs.word_of(test_word)
    m.run("minskytron")
    for _ in range(passes):
        m.run("circles")
    return [(x.v, y.v) for x, y, _ in m.state["display"]]


def simh(test_word: int, points: int) -> list[tuple[int, int]]:
    m = census.Booted(TAPE, 0o7700, [f"dep TW {test_word:o}", "dep IOS 1", f"set cpu history={ro.HISTORY}"])
    out: list[tuple[int, int]] = []
    try:
        while len(out) < points:
            m.send(f"step {CHUNK}")
            if "Step expired" not in (reply := m.read()):
                raise RuntimeError(f"simh stopped: {reply.strip()}")
            m.send(f"show cpu history={CHUNK}")
            out += [(s.ac, s.io) for s in ro.parse_history(m.read()) if s.op == "DPY"]
            m.send("set cpu history=0"); m.read()
            m.send(f"set cpu history={ro.HISTORY}"); m.read()
    finally:
        m.close()
    return out[:points]


def compare(prog: runs.Program, test_word: int, passes: int) -> str | None:
    """None when the streams agree, else the first point that differs."""
    want = simh(test_word, 3 * passes)
    got = evaluator(prog, test_word, passes)
    for k, (w, g) in enumerate(zip(want, got)):
        if w != g:
            return (f"test word {test_word:06o}: point {k} (pass {k // 3}, point {'abc'[k % 3]}): "
                    f"SIMH ({w[0]:06o}, {w[1]:06o}), RUNS ({g[0]:06o}, {g[1]:06o})")
    if len(want) != len(got):
        return f"test word {test_word:06o}: SIMH {len(want)} points, RUNS {len(got)}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("words", nargs="*", type=lambda v: int(v, 8))
    ap.add_argument("--passes", type=int, default=3000)
    ap.add_argument("--runs", type=Path, default=PROGRAM / "runs")
    a = ap.parse_args()
    rng = random.Random(1)
    words = a.words or [0, 0o777777, 0o252525, 0o525252, 0o011111, 0o707070] + \
        [rng.randrange(1 << 18) for _ in range(4)]
    prog = runs.check(runs.load(runs.source_files(a.runs)))
    failed = 0
    for w in words:
        if (diff := compare(prog, w, a.passes)) is not None:
            failed += 1
            print(f"DIFFER {diff}")
        else:
            print(f"same   test word {w:06o}: {3 * a.passes} points")
    print(f"minskytron: {len(words) - failed}/{len(words)} test words agree over {a.passes} passes")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
