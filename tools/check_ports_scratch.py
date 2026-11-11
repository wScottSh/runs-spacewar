"""Ports compiled: a scratch copy of Spacewar with `inertia_x` and `inertia_y`
replaced by one `inertia` with Ports, wired per axis at each run, and
pdp1/objects.toml's two inline entries merged into one that names it. It
must build the original image, as today's text does.

A planted defect shows the check sees the wiring: `swap` wires the x axis's
velocity and position the other way round (the image differs); `omit`
leaves the y axis's velocity unwired (the evaluator rejects the text);
`called` declares inertia a called routine (JSP), which its two wirings
cannot share (runsc refuses it).

Usage: check_ports_scratch.py [swap | omit | called]"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

import runs
import runsc

ROOT = Path(__file__).resolve().parents[1]

TEMPLATE = """processor inertia                                           # diff
  in acceleration: word
  inout velocity: word
  inout position: word
  out moved: word                                           # left in AC
  let v = acceleration + velocity
  set velocity = v
  set moved = (v >> 3) + position
  set position = moved
"""

INLINE = """[[inline]]
routine = "inertia_x"
shifts = "xct"

[[inline]]
routine = "inertia_y"
shifts = "xct"
"""


def wires(axis: str, defect: str | None) -> list[str]:
    velocity, position = f"objects.d{axis}[slot]", f"objects.{axis}[slot]"
    if defect == "swap" and axis == "x":
        velocity, position = position, velocity
    out = ["acceleration: handoff.acceleration", f"velocity: {velocity}", f"position: {position}",
           "moved: handoff.position"]
    if defect == "omit" and axis == "y":
        out.remove(f"velocity: {velocity}")
    return out


def scratch(tmp: Path, defect: str | None) -> None:
    shutil.copytree(ROOT / "runs", tmp / "runs")
    shutil.copytree(ROOT / "pdp1", tmp / "pdp1")
    prim = tmp / "runs/arithmetic.runs-prim"
    text = prim.read_text()
    old = re.search(r"processor inertia_x\(slot\).*?set objects\.y\[slot\] = handoff\.position\n", text, re.S)
    prim.write_text(text[:old.start()] + TEMPLATE + text[old.end():])
    for name in ("objects.runs", "spaceship.runs"):
        path = tmp / "runs" / name
        lines = []
        for line in path.read_text().splitlines():
            m = re.match(r"( *)run inertia_([xy])\(slot\)(.*)$", line)
            if m is None:
                lines.append(line)
                continue
            lines.append(f"{m[1]}run inertia{m[3]}")
            lines += [f"{m[1]}  {w}" for w in wires(m[2], defect)]
        path.write_text("\n".join(lines) + "\n")
    toml = tmp / "pdp1/objects.toml"
    assert INLINE in toml.read_text()
    merged = '[[place]]\nroutine = "inertia"\nconvention = "JSP"\n' if defect == "called" \
        else '[[inline]]\nroutine = "inertia"\nshifts = "xct"\n'
    toml.write_text(toml.read_text().replace(INLINE, merged))


def main() -> int:
    defect = sys.argv[1] if len(sys.argv) > 1 else None
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        scratch(tmp, defect)
        try:
            prog = runs.program(tmp / "runs")
        except runs.RunsError as e:
            print(f"rejected: {e}")
            return 1
        print("copies:", ", ".join(f"{c} = {t}({', '.join(f'{p}: {runs.text_of(e)}' for p, e in w)})"
                                   for c, (t, w) in prog.copies.items()))
        runsc.BINDINGS = tmp / "pdp1"
        try:
            code = runsc.build(prog, tmp / "out")
        except runsc.BindError as e:
            print(f"refused: {e}")
            return 1
        print(runsc.build.said, end="")
        return code


if __name__ == "__main__":
    sys.exit(main())
