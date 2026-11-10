"""The spaceship calc routine of spaceship.runs (first_spaceship and
second_spaceship) against SIMH running the oracle image.

Each call starts from one set of Records the game can hold: the object
table, the spaceship properties, the random number, the spaceship's and
the arithmetic routines' own words, the pen, the console's sense switches
and control word. In SIMH they are deposited where the PDP-1 binding places
them, the main loop's cursors are pointed at the ship's slot, its compiled
outline is loaded into the jump at sp5 as the main loop loads it, and the
routine is entered as the main loop enters it (jsp). The evaluator fires the
Network on the same Records.

The routine runs whole, through its outline. The outlines are compiled
once, into the free core after the table by the original's own outline
compiler in SIMH, and decoded into strokes (outline_code) by the RUNS one
in the evaluator; the strokes, each spelled as its member's words, must be
SIMH's words. The evaluator walks the strokes (draw_outline). So every
point is compared, the outline's included.

When the object table is full, the original halts in a loop at sr1+6; the
check redirects that halt to the stub, and the evaluator must `stop` there.

With `moved`, SIMH's compiler lays the outlines out from 05000 instead of
right after the table, and the ships' outline words point there: the
evaluator, which knows only slots of outline_code, must still match. Where
the code space lies is the binding's.

Usage: [N] [moved] (calls per routine, default 3000)."""
from __future__ import annotations

import copy
import importlib.util
import random
import sys
from collections import Counter

import pdp1
import runs
from pdp1cc import program
from pdp1cc.gate import corpus, simh
from pdp1cc.gate.simh import Inputs, STUB, CALL
from oracle_check import built_listing

spec = importlib.util.spec_from_file_location("shipref", pdp1.ROOT / "tools/check-spaceship-reference.py")
shipref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shipref)

NEG = lambda v: v ^ runs.MASK
JMP = 0o600000
RECORDS = ["objects", "ships", "random", "spaceship", "pen"]
# The arithmetic routines' own words that have a place in core.
SCRATCH = [(rec, fld) for rec, fld in pdp1.FIELDS
           if rec in ("square_root_call", "multiply_call", "integer_multiply_call", "divide_call", "sine_call")]
TWO_PI = 0o311040


def member(enum: str, name: str) -> runs.Member:
    return runs.Member(enum, name)


def signed(rng: random.Random, bits: int) -> int:
    v = rng.randrange(1 << bits)
    return NEG(v) if rng.random() < 0.5 else v


class Outlines:
    """The two outlines, compiled one after the other from the start of the
    free core: in SIMH by the original's compiler, after the table, and in
    the evaluator decoded by the RUNS one into strokes, outline_code. `at`
    is where each starts, a slot of outline_code; the strokes, each spelled
    as its member's words (pdp1.Binding.lay_out_code), must be SIMH's
    words."""

    def __init__(self, m: runs.Machine, b: pdp1.Binding):
        self.b = b
        sym = b.sym
        start, self.code = b.address("outline_code", "stroke", 0), {}
        call = m.state["outline_call"]
        call["code"] = runs.W(0)
        self.at = {}
        for shape, label, table in (("needle", "ot1", 0), ("wedge", "ot2", 0o10)):
            done, = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym["oc"], [Inputs(start, byname=sym[label])],
                                 inline=True, watch=list(range(start, start + 0o1000)))
            self.code |= {start + k: w for k, w in enumerate(done.watched) if start + k < done.ac}
            self.at[shape], call["table"] = call["code"].v, runs.W(table)
            m.run("compile_outline")
            start = done.ac
        words = b.lay_out_code(m.state["outline_code"], call["code"].v)
        if words != self.code:
            raise SystemExit("the RUNS outline compiler lays out other words than the original's")
        self.display = {a: w for a, w in self.code.items() if w == pdp1.DPY_NOWAIT}


def a_state(m: runs.Machine, rng: random.Random, outlines: Outlines) -> tuple[str, int, dict, int]:
    st = copy.deepcopy({r: m.state[r] for r in RECORDS + ["console", "controls", "launch"]
                        + sorted({r for r, _ in SCRATCH})})
    slot = rng.randrange(2)
    routine = rng.choice(["first_spaceship", "second_spaceship"])
    o, sh = st["objects"], st["ships"]
    table = rng.choice(["mixed"] * 18 + ["full", "one free"])
    free = rng.choice([1 - slot, 2, 0o26, 0o27, rng.randrange(2, 0o30)])
    for s in range(0o30):
        o["routine"][s] = member("calc_routine", rng.choice(
            ["none", "torpedo", "torpedo", "explosion"] if table == "mixed" else ["torpedo", "explosion"]))
        if table == "one free" and s == free:
            o["routine"][s] = member("calc_routine", "none")
        for f in ("x", "y", "dx", "dy", "counter", "cycles"):
            o[f][s] = runs.W(rng.randrange(1 << 18))
    o["routine"][slot] = member("calc_routine", routine)
    o["x"][slot] = runs.W(signed(rng, rng.randrange(1, 18)))
    o["y"][slot] = runs.W(signed(rng, rng.randrange(1, 18)))
    o["counter"][slot] = runs.W(rng.choice([NEG(1), NEG(2), runs.MASK, 0, 1, NEG(0o20), rng.randrange(1 << 18)]))
    o["cycles"][slot] = runs.W(rng.choice([0o2000, rng.randrange(0o10000), NEG(rng.randrange(0o10000)), 3]))
    for s in range(2):
        for f in sh:
            if f != "saved_routine":
                sh[f][s] = runs.W(rng.randrange(1 << 18))
        sh["saved_routine"][s] = member("calc_routine", ("first_spaceship", "second_spaceship")[s])
        sh["outline"][s] = runs.W(outlines.at[rng.choice(["needle", "wedge"])])
    sh["angular_momentum"][slot] = runs.W(rng.choice([0, signed(rng, 4), signed(rng, 10), rng.randrange(1 << 18)]))
    sh["angle"][slot] = runs.W(signed(rng, 17) % (TWO_PI + 1) if rng.random() < 0.9
                               else rng.choice([0, runs.MASK, TWO_PI, NEG(TWO_PI)]))
    sh["fuel"][slot] = runs.W(rng.choice([NEG(rng.randrange(1, 0o20000)), 0, runs.MASK, 1, NEG(1), NEG(2),
                                          rng.randrange(1 << 18)]))
    sh["torpedoes"][slot] = runs.W(rng.choice([NEG(1), NEG(2), NEG(0o40), 0, runs.MASK, rng.randrange(1 << 18)]))
    sh["previous_control"][slot] = runs.W(rng.choice([0, 0, rng.randrange(1 << 18)]))
    sh["jumps_left"][slot] = runs.W(rng.choice([0, runs.MASK, NEG(1), NEG(0o10), rng.randrange(1 << 18)]))
    sh["recharge"][slot] = runs.W(rng.choice([NEG(1), runs.MASK, 0, NEG(0o200), rng.randrange(1 << 18)]))
    st["random"]["number"] = runs.W(rng.randrange(1 << 18))
    for rec in ["spaceship", "pen"] + sorted({r for r, _ in SCRATCH}):
        for f, (typ, _) in m.prog.records[rec].fields.items():
            if typ == "word":
                st[rec][f] = runs.W(rng.randrange(1 << 18))
    outlines.b.share_one_word(st, RECORDS)
    st["spaceship"]["rocket"] = member("rocket", rng.choice(["off", "firing"]))
    st["launch"]["slot"] = runs.W(rng.randrange(0o30))
    sense = rng.randrange(1 << 6)
    for name, n in pdp1.SWITCHES.items():
        st["console"][name] = member("switch", "on" if sense >> (6 - n) & 1 else "off")
    source = rng.choice(["test_word"] * 4 + ["control_boxes"])
    st["controls"]["source"] = member("control_source", source)
    control = 0 if source == "control_boxes" else rng.choice(
        [rng.randrange(1 << 18), rng.randrange(1 << 18) | 0o741700,
         rng.choice([0o600000, 0o060000, 0o140000, 0o100000, 0o040000, 0o020000, 0o200000, 0o400000,
                     0o003000, 0o001400, 0o000400, 0o000200, 0o000100, 0o000003, 0])])
    st["console"]["test_word"] = runs.W(control)
    st["console"]["control_boxes"] = runs.W(0)              # headless SIMH: no buttons pressed
    return routine, slot, st, sense


def deposits(b: pdp1.Binding, st: dict, slot: int, sym: dict, image: dict) -> dict[int, int]:
    out = b.deposits(st, RECORDS)
    for rec, fld in SCRATCH:
        out[b.address(rec, fld)] = st[rec][fld].v
    mtb = sym["mtb"]
    for first, cursor, _, _ in shipref.PROPERTIES:
        at = sym[first] + slot
        out[sym[cursor]] = at if cursor in shipref.POOL_CURSORS else image[sym[cursor]] & ~0o7777 | at
    out[sym["sr1"]] = image[sym["sr1"]] & ~0o7777 | mtb + st["launch"]["slot"].v
    out[sym["sp5"]] = image[sym["sp5"]] & ~0o7777 | b.encode("ships", "outline", st["ships"]["outline"][slot])
    out[sym["cwg"]] = b.enum_word["control_source"][st["controls"]["source"].name]
    return out


def main() -> int:
    calls = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    prog = runs.program(runs.source())
    b = pdp1.Binding(prog)
    if "moved" in sys.argv[2:]:
        b.moved[("outline_code", "stroke")] = 0o5000
    sym = b.sym
    image = image_words()
    m = runs.Machine(prog)
    outlines = Outlines(m, b)
    full = sym["sr1"] + 6                                   # hlt: no space for new objects
    display = {a: w for a, w in (corpus.display_words(built_listing()) | outlines.display).items() if a != full}
    places = list(b.places(RECORDS))
    scratch = [b.address(rec, fld) for rec, fld in SCRATCH]
    watch = [p[3] for p in places] + scratch + [sym["sr1"], "PF"]
    halt_to = STUB + 4                                      # the stub's second halt: the table is full
    once = outlines.code | {full: JMP | halt_to}
    rng = random.Random(0o5700)
    cases = [a_state(m, rng, outlines) for _ in range(calls)]
    inputs = [Inputs(0, rng.randrange(1 << 18), 0, sense, st["console"]["test_word"].v)
              for _, _, st, sense in cases]
    want = run_all(cases, inputs, sym, b, image, watch, display, once)
    differ, paths = 0, Counter()
    for k, ((routine, slot, st, _), w) in enumerate(zip(cases, want)):
        m.state.update(copy.deepcopy(st))
        m.state["display"] = []
        halted = False
        since = m.writes
        try:
            m.run(routine, [slot])
        except runs.Stop:
            halted = True
        values = dict(zip(watch, w.watched))
        simh_records = b.read({a: values[a] for a in [p[3] for p in places]}, RECORDS)
        get = lambda recs, rec, fld, s: recs[rec][fld] if s is None else recs[rec][fld][s]
        outlived = b.outlived(m, RECORDS, since)
        bad = [f"{rec}.{fld}{'' if s is None else f'[{s}]'} simh {b.encode(rec, fld, get(simh_records, rec, fld, s)):06o}"
               f" runs {b.encode(rec, fld, get(m.state, rec, fld, s)):06o}"
               for rec, fld, s, _ in places if (rec, fld) not in outlived
               and get(simh_records, rec, fld, s) != get(m.state, rec, fld, s)]
        for (rec, fld), a in zip(SCRATCH, scratch):
            if values[a] != m.state[rec][fld].v:
                bad.append(f"{rec}.{fld} simh {values[a]:06o} runs {m.state[rec][fld].v:06o}")
        rocket = b.read_flags(values["PF"], ("spaceship",))["spaceship"]["rocket"]
        if rocket != m.state["spaceship"]["rocket"]:
            bad.append(f"spaceship.rocket simh {rocket.name} runs {m.state['spaceship']['rocket'].name}")
        free = (values[sym["sr1"]] & 0o7777) - sym["mtb"]
        if free != m.state["launch"]["slot"].v:
            bad.append(f"launch.slot simh {free:o} runs {m.state['launch']['slot'].v:o}")
        if (w.returned_past == halt_to - (CALL + 1)) != halted:
            bad.append(f"halted simh {w.returned_past == halt_to - (CALL + 1)} runs {halted}")
        points = [pdp1.point(p) for p in w.plotted]
        if points != m.state["display"]:
            first = next((j for j, (a, c) in enumerate(zip(points, m.state["display"])) if a != c),
                         min(len(points), len(m.state["display"])))
            bad.append(f"plotted {len(points)} simh, {len(m.state['display'])} runs, first differing {first}")
        if bad:
            differ += 1
            if differ <= 5:
                print(f"  call {k} {routine} slot {slot}: " + "; ".join(bad)[:600])
        paths.update(path(st, m.state, slot, halted))
    moved = f" (the outlines at {b.address('outline_code', 'stroke', 0):05o})" if b.moved else ""
    print(f"spaceship{moved}: {len(cases)} calls, {len(cases) - differ} match, {differ} differ; "
          f"{sum(len(w.plotted) for w in want)} points")
    print("  " + ", ".join(f"{k} {n}" for k, n in paths.most_common()))
    return 1 if differ else 0


def path(before: dict, after: dict, slot: int, halted: bool) -> list[str]:
    """Which ways a call went, from the Records the evaluator left."""
    o0, o1 = before["objects"], after["objects"]
    seen = []
    if halted:
        return ["halted: table full"]
    if o1["routine"][slot].name == "explosion":
        seen.append("exploded in the star")
    elif o1["x"][slot] == runs.W(0o377777) and o1["dx"][slot] == runs.W(0):
        seen.append("thrown to the corner")
    else:
        seen.append("drawn")
    if after["spaceship"]["gravity_x"].v or after["spaceship"]["gravity_y"].v:
        seen.append("pulled by gravity")
    if after["spaceship"]["rocket"].name == "firing":
        seen.append("thrusting")
    if after["ships"]["fuel"][slot] != before["ships"]["fuel"][slot]:
        seen.append("burned fuel")
    if any(o0["routine"][s].name == "none" and o1["routine"][s].name == "torpedo" for s in range(0o30)):
        seen.append("torpedo launched")
    if o1["routine"][slot].name == "in_hyperspace":
        seen.append("into hyperspace")
    return seen


def image_words() -> dict[int, int]:
    words, _ = program.listing(built_listing())
    return {a: int(w, 8) for a, (w, _) in words.items()}


def run_all(cases, inputs, sym, b, image, watch, display, once):
    """SIMH: each case entered at its own routine (ss1 or ss2); one session
    per routine, the results put back in case order."""
    out = [None] * len(cases)
    for routine, entry in (("first_spaceship", "ss1"), ("second_spaceship", "ss2")):
        ks = [k for k, c in enumerate(cases) if c[0] == routine]
        if not ks:
            continue
        got = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym[entry], [inputs[k] for k in ks], watch=watch, op="jsp",
                           display=display, deposits=once,
                           each=[deposits(b, cases[k][2], cases[k][1], sym, image) for k in ks])
        for k, g in zip(ks, got):
            out[k] = g
    return out


if __name__ == "__main__":
    sys.exit(main())
