"""multiply's 021 steps as 021 transitions, not a loop: writes
multiply_unrolled.net (the arc-list format) and the Record of the steps'
values from arcs/multiply.net, then verifies it like the others.

  uv run -q python docs/prototypes/graph-format/loop/unroll.py [N]"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "arcs"))
import graph, load  # noqa: E402

STEPS = 0o21
W = "multiply_steps_work"


def high(k):
    return "multiply_work.high" if k == STEPS else f"{W}.high_{k}"


def low(k):
    return {0: "multiply_work.entry_magnitude", STEPS: "multiply_work.low"}.get(k, f"{W}.low_{k}")


def main() -> int:
    src = (HERE.parent / "arcs/multiply.net").read_text().splitlines()
    keep = [l for l in src if "steps" not in l.split("#")[0]]
    places = [high(k) for k in range(STEPS)] + [low(k) for k in range(1, STEPS)]
    trans = ["  clear_high: clear"] + [f"  step_{k}: multiply_step" for k in range(1, STEPS + 1)]
    arcs = ["  clear_high.value -> " + high(0)]
    for k in range(1, STEPS + 1):
        arcs += [f"  {low(k - 1)} -> step_{k}.low", f"  multiply_work.factor_magnitude -> step_{k}.multiplicand",
                 f"  {high(k - 1)} -> step_{k}.high", f"  step_{k}.low -> {low(k)}", f"  step_{k}.high -> {high(k)}"]
    out = []
    for l in keep:
        out.append(l)
        if l == "places": out += ["  " + p for p in places]
        if l == "transitions": out += trans
        if l == "arcs": out += arcs
    (HERE / "multiply_unrolled.net").write_text("\n".join(out) + "\n")
    (HERE / f"{W}.runs").write_text(f"# The values multiply's steps hand each other, each written once.\ngame record {W}\n"
                                   + "".join(f"  {p.split('.')[1]}: word = 0\n" for p in places if p.startswith(W)))
    graph.EXTRA.append(HERE)
    return graph.verify(load.load(HERE / "multiply_unrolled.net"), int(sys.argv[1]) if len(sys.argv) > 1 else 20000)


if __name__ == "__main__":
    sys.exit(main())
