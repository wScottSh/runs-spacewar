"""G1 for the spaceship calc routine (lift/spaceship.c): the native build
against SIMH running the oracle binary.

The routine enters generated code: after it sets up the outline steps it
jumps through `sp5` into the ship's compiled outline, which jumps back to
`sq6` (outline_drawn). The native build does not run generated code, so
the check cuts the routine at that jump and runs the two halves apart:

- ss1 and ss2 (first_spaceship, second_spaceship), entered by `jsp` as the
  main loop enters them, up to the jump into the outline. In SIMH `sp5`
  jumps to the stub's second halt; natively draw_outline points to a
  stand-in that does only the same (returns one word further). The other
  way out is a ship falling into the star (`pof`), which returns to the
  first halt through `srt` (spaceship_done's exit), as the routine's own
  `dap srt` set it.
- outline_drawn (`sq6`), entered by a jump with the pool words the first
  half and the compiled outline leave (control word, heading, pen
  position, torpedo start) set at random, and `srt` patched to return.
- spaceship_in_star (`pof`), entered by a jump, `srt` patched to return.

The control word comes from `jsp i \\cwg`: in SIMH cwg names a three-word
routine in free core that loads a deposited word into IO; natively
control_word_getter points to a function returning it.

Each call sets up a ship's slot (0 or 1) the same way on both sides: every
cursor on that slot, the slot's words, every object's routine word (some
free, at least one), the random number and the sense switches; and the
homes of the pointers the torpedo launch builds. After each call the
whole object table, the random number, every pool word of the routine,
the program flags, the home words of the launch pointers and every
plotted point are compared, with where the call returned.

Usage: uv run python tools/check-spaceship-reference.py [calls per routine]"""
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from oracle_check import ROOT, built_listing, built_symbols, lifted_units, oracle_symbols
from pdp1cc import ir, program
from pdp1cc.gate import corpus, reference, simh
from pdp1cc.gate.simh import Inputs

SPACESHIP = ROOT / "lift/spaceship.c"
LIFT = [ROOT / f"lift/{f}.c" for f in
        ("tunables", "outline_compiler", "sincos", "multiply", "sqt", "divide", "objects")] + [SPACESHIP]
NOB = 0o30
MASK = ir.WORD_MASK
TWO_PI = 0o311040
CALLS = 10000

# The control word routine `\cwg` names in SIMH: dap / lio CW / jmp . (CW after it).
CW_STUB = 0o7773
CW_WORDS = [0o260000 | CW_STUB + 2, 0o220000 | CW_STUB + 3, 0o600000]
CW_IN = CW_STUB + 3

# The object table's property arrays: (first word's symbol, cursor symbol,
# native cursor name, a slot per ship only). Cursors in POOL are pool words.
PROPERTIES = [("mtb", "ml1", "routine_slot", False), ("nx1", "mx1", "x_slot", False),
              ("ny1", "my1", "y_slot", False), ("na1", "ma1", "counter_slot", False),
              ("nb1", "mb1", "cycles_slot", False), ("ndx", "mdx", "dx_slot", False),
              ("ndy", "mdy", "dy_slot", False), ("nom", "mom", "angular_momentum_slot", True),
              ("nth", "mth", "angle_slot", True), ("nfu", "mfu", "fuel_slot", True),
              ("ntr", "mtr", "torpedoes_slot", True), ("nco", "mco", "previous_control_slot", True),
              ("nh1", "mh1", "saved_routine_slot", True), ("nh2", "mh2", "jumps_left_slot", True),
              ("nh3", "mh3", "recharge_slot", True), ("nh4", "mh4", "uncertainty_slot", True)]
POOL_CURSORS = {"mdx", "mdy", "mfu", "mtr", "mh1", "mh2", "mh3", "mh4"}
LAUNCH_POINTERS = ["free_slot", "torpedo_x_slot", "torpedo_y_slot", "torpedo_counter_slot",
                   "torpedo_cycles_slot", "torpedo_dx_slot", "torpedo_dy_slot"]
SQ6_INPUTS = ["control_word", "heading_sine", "heading_cosine", "ship_x", "ship_y",
              "torpedo_start_x", "torpedo_start_y"]


def neg(v: int) -> int:
    return v ^ MASK


@dataclass
class State:
    slot: int
    table: dict[int, int]           # table offset -> word, the words this call sets
    ran: int
    control: int
    pool: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Routine:
    name: str
    op: str                         # jsp, or jmp for a block
    random_pool: bool = False       # outline_drawn: its pool inputs set at random


ROUTINES = [Routine("first_spaceship", "jsp"), Routine("second_spaceship", "jsp"),
            Routine("outline_drawn", "jmp", True), Routine("spaceship_in_star", "jmp")]


def signed(rng: random.Random, bits: int) -> int:
    v = rng.randrange(1 << bits)
    return neg(v) if rng.random() < 0.5 else v


def position(rng: random.Random) -> int:
    """Any distance from the star: inside the capture radius, in reach of
    gravity, and beyond."""
    return signed(rng, rng.randrange(1, 18))


def random_state(rng: random.Random, offsets: dict[str, int], routine: Routine) -> State:
    slot = rng.randrange(2)
    table = {}
    free = [rng.random() < 0.3 for _ in range(NOB)]
    if not any(free):
        free[rng.randrange(NOB)] = True
    for k in range(NOB):
        table[offsets["mtb"] + k] = 0 if free[k] else rng.randrange(1, 1 << 18)
    for first, _, _, ship in PROPERTIES[1:]:
        table[offsets[first] + slot] = rng.randrange(1 << 18)
    table[offsets["nx1"] + slot] = position(rng)
    table[offsets["ny1"] + slot] = position(rng)
    table[offsets["na1"] + slot] = rng.choice([neg(1), neg(2), MASK, 0, 1, neg(0o20), rng.randrange(1 << 18)])
    table[offsets["nb1"] + slot] = rng.choice([0o2000, rng.randrange(0o10000), neg(rng.randrange(0o10000))])
    table[offsets["nom"] + slot] = rng.choice([0, signed(rng, 4), signed(rng, 10), rng.randrange(1 << 18)])
    table[offsets["nth"] + slot] = signed(rng, 17) % (TWO_PI + 1) if rng.random() < 0.9 else \
        rng.choice([0, MASK, TWO_PI, neg(TWO_PI)])
    table[offsets["nfu"] + slot] = rng.choice([neg(rng.randrange(1, 0o20000)), 0, MASK, 1, neg(1), neg(2),
                                               rng.randrange(1 << 18)])
    table[offsets["ntr"] + slot] = rng.choice([neg(1), neg(2), neg(0o40), 0, MASK, rng.randrange(1 << 18)])
    table[offsets["nco"] + slot] = rng.choice([0, 0, rng.randrange(1 << 18)])
    table[offsets["nh2"] + slot] = rng.choice([0, MASK, neg(1), neg(0o10), rng.randrange(1 << 18)])
    table[offsets["nh3"] + slot] = rng.choice([neg(1), MASK, 0, neg(0o200), rng.randrange(1 << 18)])
    control = rng.choice([rng.randrange(1 << 18), rng.randrange(1 << 18) | 0o741700,
                          rng.choice([0o600000, 0o060000, 0o140000, 0o100000, 0o040000, 0o020000,
                                      0o200000, 0o400000, 0o003000, 0o001400, 0o000400, 0])])
    pool = {}
    if routine.random_pool:
        pool = {"control_word": control, "heading_sine": signed(rng, 17), "heading_cosine": signed(rng, 17),
                "ship_x": rng.randrange(1 << 18), "ship_y": rng.randrange(1 << 18),
                "torpedo_start_x": rng.randrange(1 << 18), "torpedo_start_y": rng.randrange(1 << 18)}
    return State(slot, table, rng.randrange(1 << 18), control, pool)


def native(routine: Routine, unit: ir.Unit, address: dict[str, int], placed, states: list[State],
           offsets: dict[str, int], size: int, watch: list[str]) -> Path:
    rows = ",\n".join("{" + f"{s.slot}u, 0{s.ran:o}u, 0{s.control:o}u, {len(s.table)}u" + "}" for s in states)
    sets = ",\n".join(", ".join(f"{{0{k:o}u, 0{v:o}u}}" for k, v in sorted(s.table.items())) for s in states)
    defined = {n for n, st in unit.objects.items() if isinstance(st, ir.Homed) and st.here}
    cursors = "".join(f"word *{name};\n" for _, _, name, _ in PROPERTIES if name not in defined)
    points = "\n".join(f"    {name} = &object_table[0{offsets[first]:o}u + slot];"
                       for first, _, name, _ in PROPERTIES)
    pool = "".join(f"    {name} = word::bits(pdp1_pool[n][{k}]);\n" for k, name in enumerate(SQ6_INPUTS))
    pool_rows = ",\n".join("{" + ", ".join(f"0{s.pool.get(n, 0):o}u" for n in SQ6_INPUTS) + "}" for s in states)
    launch = "".join(f"    {name} = object_table;\n" for name in LAUNCH_POINTERS)
    scratch = (f"word object_table[0{size:o}];\n" + cursors
               + "static word pdp1_control;\n"
               + "static word pdp1_controls() { return pdp1_control; }\n"
               + "control_word_reader *control_word_getter;\n"
               + "static int pdp1_outline_entered;\n"
               + "static void pdp1_outline() { pdp1_outline_entered = 1; }\n"
               + f"static const unsigned pdp1_states[][4] = {{\n{rows}\n}};\n"
               + f"static const unsigned pdp1_sets[] [2] = {{\n{sets}\n}};\n"
               + f"static const unsigned pdp1_pool[][{len(SQ6_INPUTS)}] = {{\n{pool_rows}\n}};\n"
               + "static unsigned pdp1_next_set;\n"
               + "static void pdp1_setup(unsigned n) {\n"
               + "    const unsigned *s = pdp1_states[n];\n    unsigned slot = s[0];\n"
               + "    for (unsigned k = 0; k < s[3]; ++k, ++pdp1_next_set)\n"
               + "        object_table[pdp1_sets[pdp1_next_set][0]] = word::bits(pdp1_sets[pdp1_next_set][1]);\n"
               + points + "\n" + launch
               + "    random_number = word::bits(s[1]);\n    pdp1_control = word::bits(s[2]);\n"
               + "    control_word_getter = pdp1_controls;\n    draw_outline = pdp1_outline;\n"
               + "    pdp1_outline_entered = 0;\n"
               + (pool if routine.random_pool else "") + "}\n")
    placed = placed + [reference.Placement("object_table", size, address["mtb"])]
    sig = unit.signatures[routine.name]
    # In SIMH `sp5` jumps to the stub's second halt: the outline counts as a return one word further.
    call = f"({reference.call_expr(sig)}, pdp1_skips = pdp1_outline_entered, word())"
    return reference.build(LIFT, ROOT / "build/ref" / routine.name, call,
                           watch=watch, placed=placed, scratch=scratch, setup="pdp1_setup(ac);")


def deposits(state: State, address: dict[str, int], image: dict[int, int], offsets: dict[str, int],
             unit: ir.Unit) -> dict[int, int]:
    mtb = address["mtb"]
    out = {mtb + k: v for k, v in state.table.items()}
    for first, cursor, _, _ in PROPERTIES:
        at = address[first] + state.slot
        out[address[cursor]] = at if cursor in POOL_CURSORS else image[address[cursor]] & ~ir.ADDR_MASK | at
    for name in LAUNCH_POINTERS:
        home = address[unit.objects[name].sym]
        out[home] = image[home] & ~ir.ADDR_MASK | mtb
    sp5 = address["sp5"]
    out[sp5] = image[sp5] & ~ir.ADDR_MASK | simh.CALL + 2
    out[address["ran"]] = state.ran
    out[CW_IN] = state.control
    for name, v in state.pool.items():
        out[address[unit.objects[name].sym]] = v
    return out


def compare(label: str, calls, want, got, names: list[str]) -> int:
    diffs = []
    for n, (c, w, g) in enumerate(zip(calls, want, got)):
        bad = [f"{k} simh {a:06o} native {b:06o}" for k, a, b in zip(names, w.watched, g.watched) if a != b]
        if w.returned_past != g.returned_past:
            bad.append(f"returned past call+1 by {w.returned_past} in simh, {g.returned_past} native")
        if w.plotted != g.plotted:
            k = next((k for k, (a, b) in enumerate(zip(w.plotted, g.plotted)) if a != b),
                     min(len(w.plotted), len(g.plotted)))
            bad.append(f"plotted {len(w.plotted)} simh, {len(g.plotted)} native, first differing point {k}")
        if bad:
            diffs.append(f"call {n} (sense {c.sense:02o}): " + ", ".join(bad))
    if len(want) != len(got):
        diffs.append(f"{len(want)} simh results, {len(got)} native")
    points = sum(len(w.plotted) for w in want)
    print(f"{label}: {len(calls)} calls, {len(calls) - len(diffs)} match, {len(diffs)} differ; "
          f"{points} points plotted, {len(names)} words compared after each")
    for d in diffs[:10]:
        print("  " + d[:400])
    return 1 if diffs else 0


def paths(routine: Routine, states: list[State], want, address: dict[str, int], offsets: dict[str, int],
          watch_names: list[str]) -> str:
    """Which ways the calls went, from what the machine did."""
    seen = Counter()
    for s, w in zip(states, want):
        words = dict(zip(watch_names, w.watched))
        if routine.op == "jsp":
            seen["into the outline" if w.returned_past == 1 else "into the star"] += 1
            if words["star_vector_x"] or words["star_vector_y"]:
                seen["pulled by gravity"] += 1
            if words["program flags"] & 1:
                seen["thrusting"] += 1
            continue
        routine_word = words[f"table {offsets['mtb'] + s.slot:03o}"]
        launched = sum(1 for k in range(NOB) if s.table[offsets["mtb"] + k] == 0
                       and words[f"table {offsets['mtb'] + k:03o}"] == address["tcr"])
        if launched:
            seen["torpedo launched"] += 1
        if routine_word == address["hp1"] | 0o400000:
            seen["into hyperspace"] += 1
        if routine_word == address["mex"] | 0o400000:
            seen["exploded"] += 1
        if w.plotted:
            seen["flame drawn"] += 1
    return ", ".join(f"{k} {n}" for k, n in seen.most_common())


def main(calls_per_routine: int = CALLS) -> int:
    address = oracle_symbols() | built_symbols()
    units = lifted_units(LIFT)
    unit = units[SPACESHIP]
    placed = [p for u in units.values() for p in reference.placements(u, address)]
    display = corpus.display_words(built_listing())
    words, _ = program.listing(built_listing())
    image = {a: int(w, 8) for a, (w, _) in words.items()}
    mtb, size = address["mtb"], address["nnn"] - address["mtb"]
    offsets = {first: address[first] - mtb for first, *_ in PROPERTIES}

    cursor_names = {name for *_, name, _ in PROPERTIES}
    pool = [(name, s.sym) for name, s in unit.objects.items() if isinstance(s, ir.Pool)
            and s.sym in address and name not in cursor_names and name != "control_word_getter"]
    watch = [(f"table {k:03o}", mtb + k, f"object_table[0{k:o}]") for k in range(size)]
    watch += [("ran", address["ran"], "random_number")]
    watch += [(name, address[sym], name) for name, sym in pool]
    watch += [("program flags", "PF", "word::bits(pdp1_program_flags)")]
    for name in LAUNCH_POINTERS:
        home = address[unit.objects[name].sym]
        watch.append((f"home of {name}", home,
                      f"word::bits(0{image[home] & ~ir.ADDR_MASK:o}u | pdp1_address({name}))"))

    failed = 0
    for n, routine in enumerate(ROUTINES):
        rng = random.Random(0o6000 + n)
        count = calls_per_routine if routine.name != "spaceship_in_star" else calls_per_routine // 4
        states = [random_state(rng, offsets, routine) for _ in range(count)]
        senses = [rng.randrange(1 << 6) for _ in states]
        calls = [Inputs(k, 0, 0, senses[k]) for k in range(len(states))]
        sym = unit.signatures[routine.name].sym
        once = {address["cwg"]: CW_STUB} | {CW_STUB + k: w for k, w in enumerate(CW_WORDS[:3])}
        if routine.op == "jmp":
            once[address[unit.signatures["spaceship_done"].sym]] = 0o600000 | simh.CALL + 1
        want = simh.run_jda(ROOT / "build/pdp1", ROOT / "build/oracle.rim", address[sym], calls,
                            watch=[a for _, a, _ in watch], op=routine.op, display=display, deposits=once,
                            each=[deposits(s, address, image, offsets, unit) for s in states])
        got = reference.run(native(routine, unit, address, placed, states, offsets, size,
                                   [w for *_, w in watch]), calls)
        failed |= compare(routine.name, calls, want, got, [k for k, *_ in watch])
        print("  " + paths(routine, states, want, address, offsets, [k for k, *_ in watch]))
    return failed


if __name__ == "__main__":
    sys.exit(main(*(int(a) for a in sys.argv[1:2])))
