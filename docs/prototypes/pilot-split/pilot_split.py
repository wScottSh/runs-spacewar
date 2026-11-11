"""Throwaway prototype for "Hand-decompose a few Processors of the pilot" (#51).

Each variant splits pilot Processors in a scratch copy of runs/ and pdp1/ and
compiles it. KEEPDIR=<dir> keeps the scratch copy; DECL picks the inertia
split's declarations (network | pieces).

  uv run python docs/prototypes/pilot-split/pilot_split.py inertia
  DECL=pieces uv run python docs/prototypes/pilot-split/pilot_split.py inertia_split
  uv run python docs/prototypes/pilot-split/pilot_split.py sine_copies
  uv run python docs/prototypes/pilot-split/pilot_split.py sine_atoms docs/prototypes/pilot-split/sine_constants.runs
  uv run python docs/prototypes/pilot-split/pilot_split.py multiply_net"""
from __future__ import annotations
import re, shutil, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import runs, runsc, check_ports_scratch as cps  # noqa: E402

INERTIA_SPLIT = """processor accumulate                                        # add; dac
  in amount: word
  inout total: word
  set total = amount + total

processor drift                                             # sar 3s; add; dac
  in velocity: word
  inout position: word
  out moved: word
  set moved = (velocity >> 3) + position
  set position = moved

network inertia                                             # diff
  in acceleration: word
  inout velocity: word
  inout position: word
  out moved: word
  run accumulate
    amount: acceleration
    total: velocity
  run drift
"""

INERTIA_OWNED = """processor sum                                               # add
  in augend: word
  in addend: word
  out total: word
  set total = augend + addend

processor pass                                              # dac
  in source: word
  out target: word
  set target = source

processor drift                                             # sar 3s; add; dac
  in velocity: word
  inout position: word
  out moved: word
  set moved = (velocity >> 3) + position
  set position = moved

network inertia                                             # diff
  in acceleration: word
  inout velocity: word
  inout position: word
  out moved: word
  owns v: word                                              # the new velocity, kept in AC
  run sum
    augend: acceleration
    addend: velocity
    total: v
  run pass
    source: v
    target: velocity
  run drift
    velocity: v
"""

def sub(text, old, new):
    assert old in text, old[:60]
    return text.replace(old, new)

def cut(tmp: Path, name: str) -> None:
    prim = tmp / "runs/arithmetic.runs-prim"
    if name in ("inertia", "inertia_split"):
        cps.scratch(tmp, None)
    t = prim.read_text()
    if name in ("inertia", "inertia_split"):
        if name == "inertia_split":
            import os
            t = sub(t, cps.TEMPLATE, INERTIA_OWNED if os.environ.get("OWNED") else INERTIA_SPLIT)
            import os
            decl = os.environ.get("DECL", "network")
            toml = tmp / "pdp1/objects.toml"
            one = '[[inline]]\nroutine = "inertia"\nshifts = "xct"\n'
            if decl == "pieces":
                toml.write_text(sub(toml.read_text(), one, '[[inline]]\nroutine = "accumulate"\n\n[[inline]]\nroutine = "drift"\nshifts = "xct"\n'))
            elif decl == "drift":
                toml.write_text(sub(toml.read_text(), one, '[[inline]]\nroutine = "drift"\nshifts = "xct"\n'))
    elif name == "sine_atoms":
        # every step between the multiplies is copies and one add
        start = t.index("processor sine_x  ")
        end = t.index("processor sine_answer")
        t = t[:start] + SINE_ATOMS + t[end:]
        net = re.search(r"network sine  .*?run sine_answer\n", t, re.S)
        t = t[:net.start()] + SINE_NET + t[net.end():]
    elif name == "sine_copies":
        start = t.index("processor sine_x  ")
        end = t.index("processor sine_answer")
        t = t[:start] + SINE_ATOMS + SINE_KEEP + t[end:]
        net = re.search(r"network sine  .*?run sine_answer\n", t, re.S)
        t = t[:net.start()] + SINE_NET2 + t[net.end():]
    elif name in ("multiply_net", "arith_net", "sqrt_net"):
        here = Path(__file__).parent
        start = t.index("processor multiply  ")
        end = t.index("# BBN integer multiply (imp)")
        t = t[:start] + (here / "atoms.txt").read_text() + (here / "multiply_net.txt").read_text() + "\n" + t[end:]
        if name in ("sqrt_net", "arith_net"):
            start = t.index("processor square_root  ")
            end = t.index("# Sine and cosine")
            t = t[:start] + (here / "sqrt_net.txt").read_text() + "\n" + t[end:]
        if name == "arith_net":
            start = t.index("processor divide  ")
            end = t.index("# BBN integer divide (idv)")
            t = t[:start] + (here / "divide_net.txt").read_text() + "\n" + t[end:]
    prim.write_text(t)

SINE_ATOMS = """processor copy                                              # lac; dac
  in source: word
  out target: word
  set target = source

processor add                                               # add
  in augend: word
  in addend: word
  out sum: word
  set sum = augend + addend

"""
SINE_NET = """network sine                                                # sin
  writes: sine_call, multiply_call
  run sine_reduce
  run multiply
  run copy                                                  # dac sin
    source: multiply_call.partial
    target: sine_call.x
  run copy
    source: sine_call.x
    target: multiply_call.entry
  run copy                                                  # mult sin
    source: sine_call.x
    target: multiply_call.factor
  run multiply
  run copy                                                  # dac cos
    source: multiply_call.partial
    target: sine_call.x_squared
  run copy
    source: sine_call.x_squared
    target: multiply_call.entry
  run copy                                                  # mult (756103
    source: sine_constants.c7
    target: multiply_call.factor
  run multiply
  run add                                                   # add (121312
    augend: multiply_call.partial
    addend: sine_constants.c5
    sum: multiply_call.entry
  run copy                                                  # mult cos
    source: sine_call.x_squared
    target: multiply_call.factor
  run multiply
  run add                                                   # add (532511
    augend: multiply_call.partial
    addend: sine_constants.c3
    sum: multiply_call.entry
  run copy
    source: sine_call.x_squared
    target: multiply_call.factor
  run multiply
  run add                                                   # add (144417
    augend: multiply_call.partial
    addend: sine_constants.c1
    sum: multiply_call.entry
  run copy                                                  # mult sin
    source: sine_call.x
    target: multiply_call.factor
  run multiply
  run sine_answer
"""

SINE_KEEP = """processor sine_c7
  writes: multiply_call
  set multiply_call.factor = -021674

processor sine_term_5
  writes: multiply_call
  set multiply_call.entry = multiply_call.partial + 0121312

processor sine_term_3
  writes: multiply_call
  set multiply_call.entry = multiply_call.partial + -0245266

processor sine_term_1
  writes: multiply_call
  set multiply_call.entry = multiply_call.partial + 0144417

"""
SINE_NET2 = SINE_NET
for c, r in (("c7", None), ("c5", "sine_term_5"), ("c3", "sine_term_3"), ("c1", "sine_term_1")):
    if r is None:
        SINE_NET2 = SINE_NET2.replace("""  run copy                                                  # mult (756103
    source: sine_constants.c7
    target: multiply_call.factor
""", "  run sine_c7\n")
    else:
        SINE_NET2 = re.sub(r"  run add .*\n.*\n    addend: sine_constants.%s\n.*\n" % c, "  run %s\n" % r, SINE_NET2)


def main():
    name = sys.argv[1]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        import os
        if os.environ.get('KEEPDIR'): tmp = Path(os.environ['KEEPDIR']); shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
        if name not in ("inertia", "inertia_split"):
            shutil.copytree(ROOT / "runs", tmp / "runs")
            shutil.copytree(ROOT / "pdp1", tmp / "pdp1")
        cut(tmp, name)
        extra = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        if extra:
            (tmp / "runs" / extra.name).write_text(extra.read_text())
        try:
            prog = runs.program(tmp / "runs")
        except runs.RunsError as e:
            print(f"rejected: {e}"); return 1
        print("copies:", ", ".join(f"{c}={t}" for c, (t, w) in prog.copies.items()))
        runsc.BINDINGS = tmp / "pdp1"
        try:
            code = runsc.build(prog, tmp / "out")
        except runsc.BindError as e:
            print(f"refused: {e}"); return 1
        print(runsc.build.said.strip().splitlines()[-1]); return code

if __name__ == "__main__":
    sys.exit(main())
