"""The outline compiler of runs/outlines/ against SIMH running the oracle
image's oc, word for word: the strokes it decodes, each encoded as the
words its member's arm of draw_outline compiles to (its TEMPLATE).

1. One outline at a time: the needle and the wedge from the tape, and
   synthetic outlines (after check-outline-reference.py) that
   use every direction code in every position of a word, reach the 7 code
   first, in the middle and last in a word, and after a store and after a
   restore. SIMH runs `jda oc` with the code space's start in AC and the
   outline's address after the call; the evaluator runs compile_outline
   with outline_call.code at 0. Compared: every word the compiler lays
   out, where the code ends, the compiler's own words (occ, oci, the
   jump ocm, the outline word ocg reads) and flag 6.
2. A new game (a2), for each setting of separate_outlines (ddd): -0 and
   +0, and other words of either sign. Compared: where each ship's outline
   starts, and every word of the code space up to the end of the last.

The evaluator's strokes are encoded by the PDP-1 binding (tools/pdp1.py):
each member's words, at the addresses where the binding places each
Record. Usage: no arguments."""
from __future__ import annotations

import random
import sys

import pdp1
import runs
from pdp1cc.gate import simh
from pdp1cc.gate.simh import Inputs, STUB

JMP = 0o600000
AREA = 0o1000

SYNTHETIC = {
    "every code, in order then reversed (one store)": [0o012345, 0o654321, 0o700000],
    "7 first in the outline": [0o700000],
    "7 in the middle of a word, later codes ignored": [0o123756],
    "7 as the last code of a word": [0o111111, 0o222227],
    "7 after a store (flag 6 left set)": [0o616161, 0o600000, 0o670000],
    "7 after a restore (flag 6 left clear)": [0o606000, 0o700000],
    "codes 0 and 1 interleaved, then 2..5 runs": [0o010101, 0o222333, 0o444555, 0o102345, 0o700000],
}


def code_words(m: runs.Machine, b: pdp1.Binding, end: int) -> list[int]:
    """The strokes before end as words; sets where each lies (b.code_slots)."""
    words = b.lay_out_code(m.state["outline_code"], end)
    return [words[a] for a in sorted(words)]


def one_outline(prog: runs.Program, b: pdp1.Binding) -> int:
    sym = b.sym
    nnn = sym["nnn"]
    cases = [("needle (ot1)", None, 0), ("wedge (ot2)", None, 0o10)] + \
        [(name, table, 0) for name, table in SYNTHETIC.items()]
    own = [b.address("outline_compiler", f) for f in ("codes_left", "codes_rest", "start_over")]
    watch = list(range(nnn, nnn + AREA)) + own + [sym["ocg"], "PF"]
    differ = 0
    for name, table, start in cases:
        deposits = {b.address("outlines", "codes", start + k): w for k, w in enumerate(table or [])}
        done, = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym["oc"],
                             [Inputs(nnn, byname=b.address("outlines", "codes", start))],
                             inline=True, watch=watch, deposits=deposits)
        m = runs.Machine(prog)
        for k, w in enumerate(table or []):
            m.state["outlines"]["codes"][start + k] = runs.W(w)
        m.state["outline_call"]["code"] = runs.W(0)
        m.state["outline_call"]["table"] = runs.W(start)
        m.run("compile_outline")
        end = m.state["outline_call"]["code"].v
        values = dict(zip(watch, done.watched))
        bad = []
        want, got = list(done.watched[:done.ac - nnn]), code_words(m, b, end)
        if done.ac != b.encode("outline_call", "code", m.state["outline_call"]["code"]):
            bad.append(f"ends simh {done.ac - nnn:o} runs {b.encode('outline_call', 'code', m.state['outline_call']['code']) - nnn:o}")
        if want != got:
            k = next((k for k, (w, g) in enumerate(zip(want, got)) if w != g), min(len(want), len(got)))
            bad.append(f"code differs from word {k:o}")
        oc = m.state["outline_compiler"]
        for f, a in zip(("codes_left", "codes_rest", "start_over"), own):
            if values[a] != b.encode("outline_compiler", f, oc[f]):
                bad.append(f"outline_compiler.{f} simh {values[a]:06o} runs {b.encode('outline_compiler', f, oc[f]):06o}")
        if values[sym["ocg"]] & 0o7777 != b.encode("outline_compiler", "table", oc["table"]):
            bad.append("outline_compiler.table differs")
        six = b.read_flags(values["PF"], ("outline_compiler",))["outline_compiler"]["six"]
        if six != oc["six"]:
            bad.append(f"outline_compiler.six simh {six.name} runs {oc['six'].name}")
        print(f"  {name:<48} {end:>4o} strokes, {len(got):>4o} words (octal), the next 6 code {oc['six'].name}s"
              + (": " + "; ".join(bad) if bad else ""))
        differ += bool(bad)
    print(f"outline compiler: {len(cases)} outlines, {len(cases) - differ} match, {differ} differ")
    return differ


def new_games(prog: runs.Program, b: pdp1.Binding) -> int:
    sym = b.sym
    nnn = sym["nnn"]
    rng = random.Random(0o3772)
    settings = [runs.MASK, 0] + [rng.randrange(1 << 18) for _ in range(4)]
    watch = list(range(nnn, nnn + 2 * AREA)) + [b.address("ship_outlines", "outline", s) for s in (0, 1)]
    got = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym["a2"], [Inputs(0) for _ in settings], op="jmp",
                       watch=watch, deposits={sym["ml0"]: JMP | STUB + 3},
                       each=[{b.address("outline_setting", "separate_outlines"): ddd} for ddd in settings])
    differ = 0
    for ddd, done in zip(settings, got):
        m = runs.Machine(prog)
        m.state["outline_setting"]["separate_outlines"] = runs.W(ddd)
        m.run("new_game")
        end = m.state["outline_call"]["code"].v
        got = code_words(m, b, end)
        starts = [b.encode("ship_outlines", "outline", w) for w in m.state["ship_outlines"]["outline"]]
        bad = []
        if list(done.watched[-2:]) != starts:
            bad.append(f"outlines start simh {[f'{w:o}' for w in done.watched[-2:]]} runs {[f'{w:o}' for w in starts]}")
        if list(done.watched[:len(got)]) != got:
            bad.append("code differs")
        shared = starts[0] == starts[1]
        print(f"  separate_outlines {ddd:06o}: {'one outline, shared' if shared else 'an outline each'}, "
              f"{end:o} strokes, {len(got):o} words" + (": " + "; ".join(bad) if bad else ""))
        differ += bool(bad)
    print(f"new game: {len(settings)} settings of separate_outlines, {len(settings) - differ} match, {differ} differ")
    return differ


def main() -> int:
    prog = runs.program(runs.source())
    b = pdp1.Binding(prog)
    return 1 if one_outline(prog, b) + new_games(prog, b) else 0


if __name__ == "__main__":
    sys.exit(main())
