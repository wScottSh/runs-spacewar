"""G1 for the object calc routines (lift/objects.c): the native build
against SIMH running the oracle binary.

Each call sets up one object first, the same way on both sides: a slot of
the object table (a ship's slot for the routines that use the ship-only
properties), every cursor pointed at that slot, the slot's words, the
random number and the sense switches. In SIMH the cursors are the main
loop's and the spaceship calc routine's instruction words and pool words,
deposited with the slot's addresses; natively they are the C pointers,
pointed into a table laid out as the machine's. Then the routine runs once,
entered as the main loop enters it (`jsp`).

After each call the whole object table, the random number, the particle
count and the heading pass count are compared, and for
the explosion the two words it builds (the `xct` that picks the spread and
the shift run in place); so is every point plotted, in order.

Each routine gets seeded random objects plus edge states: counters about
to expire and just past it, the hyperspace jump count and uncertainty at
their limits.

Usage: uv run python tools/check-objects-reference.py"""
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from oracle_check import ROOT, built_listing, built_symbols, lifted_units, oracle_symbols
from pdp1cc import ir
from pdp1cc.gate import corpus, reference, simh
from pdp1cc.gate.simh import Inputs

OBJECTS = ROOT / "lift/objects.c"
LIFT = [ROOT / "lift/tunables.c", ROOT / "lift/outline_compiler.c", OBJECTS]
RANDOM_CALLS = 10000
NOB = 0o30                          # objects in the table: two ships and the torpedoes
SHIPS = 2
MASK = ir.WORD_MASK

# The table's property arrays, by their first word's symbol: the cursor
# that walks each (its Macro symbol) and its native name.
PROPERTIES = [("mtb", "ml1", "routine_slot"), ("nx1", "mx1", "x_slot"), ("ny1", "my1", "y_slot"),
              ("na1", "ma1", "counter_slot"), ("nb1", "mb1", "cycles_slot"),
              ("ndx", "mdx", "dx_slot"), ("ndy", "mdy", "dy_slot"), ("nth", "mth", "angle_slot"),
              ("nh1", "mh1", "saved_routine_slot"), ("nh2", "mh2", "jumps_left_slot"),
              ("nh3", "mh3", "recharge_slot"), ("nh4", "mh4", "uncertainty_slot")]
POOL_CURSORS = {"mdx", "mdy", "mh1", "mh2", "mh3", "mh4"}   # pool words; the rest are address fields
SHIP_ONLY = {"nth", "nh1", "nh2", "nh3", "nh4"}              # arrays with a slot per ship only


def index(first: str) -> str:
    """The slot a property's cursor points at, natively: a ship-only
    property of a torpedo's state goes to a ship's slot, inside its array."""
    return f"slot % {SHIPS}u" if first in SHIP_ONLY else "slot"


@dataclass(frozen=True)
class State:
    slot: int
    words: tuple[int, ...]          # one per property, in PROPERTIES order
    ran: int


def neg(v: int) -> int:
    return v ^ MASK


COUNTER_EDGES = [neg(1), neg(2), MASK, 0, 1, 0o377777, 0o400000, neg(0o10), neg(0o100)]


def random_states(rng: random.Random, n: int, ship: bool, cycles) -> list[State]:
    out = []
    for _ in range(n):
        words = [rng.randrange(1 << 18) for _ in PROPERTIES]
        words[3] = rng.choice(COUNTER_EDGES + [rng.randrange(1 << 18)] * 4)
        words[4] = cycles(rng)
        out.append(State(rng.randrange(SHIPS if ship else NOB), tuple(words), rng.randrange(1 << 18)))
    return out


def explosion_cycles(rng: random.Random) -> int:
    """A ship's 2000 or a torpedo's 20, or any count up to 3777 either way."""
    return rng.choice([0o2000, 0o20, rng.randrange(0o4000), neg(rng.randrange(0o4000))])


def any_word(rng: random.Random) -> int:
    return rng.randrange(1 << 18)


def edges(base: State, field: int, values: list[int]) -> list[State]:
    return [State(base.slot, base.words[:field] + (v,) + base.words[field + 1:], base.ran) for v in values]


@dataclass(frozen=True)
class Routine:
    name: str                       # C name
    sym: str                        # how SIMH finds it: a symbol of the build
    op: str                         # jsp, or jmp for a block
    ship: bool                      # uses the ship-only properties
    cycles: object
    extra_edges: tuple = ()         # (property index, values)


ROUTINES = [
    Routine("explosion", "mex", "jsp", False, explosion_cycles,
            ((4, [0, 1, 7, 0o10, 0o1137, 0o1140, 0o1147, 0o377777, MASK, neg(0o1140)]),)),
    Routine("torpedo", "tcr", "jsp", False, any_word),
    Routine("in_hyperspace", "hp1", "jsp", True, any_word),
    Routine("breakout", "", "jsp", True, any_word,
            ((9, [neg(1), MASK, 0, neg(0o10), 0o377777]),
             (11, [0, 0o340000, 0o377777, 0o400000, neg(0o40000), MASK]))),
]


def idle_cursors() -> list[str]:
    """Pool cursors object_table.h declares that no calc routine here uses:
    the main loop and the spaceship calc routine walk them. The native
    build defines them so the address table can name them."""
    header = (ROOT / "lift/object_table.h").read_text()
    used = {name for *_, name in PROPERTIES}
    return [n for n in re.findall(r"extern POOL word \*(\w+)", header) if n not in used]


def native(routine: Routine, unit: ir.Unit, address: dict[str, int], placed,
           states: list[State], watch: list[str]) -> Path:
    mtb, nnn = address["mtb"], address["nnn"]
    rows = ",\n".join("{" + ", ".join(f"0{v:o}u" for v in (s.slot, *s.words, s.ran)) + "}"
                      for s in states)
    points = "\n".join(f"    {name} = &pdp1_table[0{address[first] - mtb:o}u + {index(first)}];"
                       f" *{name} = word::bits(s[{k + 1}]);"
                       for k, (first, _, name) in enumerate(PROPERTIES))
    scratch = (f"word pdp1_table[0{nnn - mtb:o}];\n"
               + "".join(f"word *{name};\n" for _, cursor, name in PROPERTIES if cursor not in POOL_CURSORS)
               + "".join(f"word *{name};\n" for _, cursor, name in PROPERTIES if cursor in POOL_CURSORS)
               + "".join(f"word *{name};\n" for name in idle_cursors())
               + f"static const unsigned pdp1_states[][{len(PROPERTIES) + 2}] = {{\n{rows}\n}};\n"
               + "static void pdp1_setup(unsigned n) {\n"
               + "    const unsigned *s = pdp1_states[n];\n    unsigned slot = s[0];\n"
               + points + f"\n    random_number = word::bits(s[{len(PROPERTIES) + 1}]);\n}}\n")
    sig = unit.signatures[routine.name]
    return reference.build(LIFT, ROOT / "build/ref" / routine.name, reference.call_expr(sig),
                           watch=watch, placed=placed, scratch=scratch, setup="pdp1_setup(ac);")


def cursor_deposits(state: State, address: dict[str, int], image: dict[int, int]) -> dict[int, int]:
    """Point every cursor at the state's slot and fill the slot."""
    out = {}
    for (first, cursor, _), word in zip(PROPERTIES, state.words):
        at = address[first] + (state.slot % SHIPS if first in SHIP_ONLY else state.slot)
        if cursor in POOL_CURSORS:
            out[address[cursor]] = at
        else:
            out[address[cursor]] = image[address[cursor]] & ~ir.ADDR_MASK | at
        out[at] = word
    out[address["ran"]] = state.ran
    return out


def image_words(address: dict[str, int]) -> dict[int, int]:
    """The oracle's words at the cursors' homes, from the build's listing."""
    from pdp1cc import program
    words, _ = program.listing(built_listing())
    return {a: int(w, 8) for a, (w, _) in words.items()}


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
            diffs.append(f"call {n} (sense {c.sense:02o}, io {c.io:06o}): " + ", ".join(bad))
    if len(want) != len(got):
        diffs.append(f"{len(want)} simh results, {len(got)} native")
    points = sum(len(w.plotted) for w in want)
    print(f"{label}: {len(calls)} calls, {len(calls) - len(diffs)} match, {len(diffs)} differ; "
          f"{points} points plotted, {len(names)} words compared after each")
    for d in diffs[:10]:
        print("  " + d[:400])
    return 1 if diffs else 0


def main() -> int:
    address = oracle_symbols() | built_symbols()
    units = lifted_units(LIFT)
    unit = units[OBJECTS]
    placed = [p for u in units.values() for p in reference.placements(u, address)]
    display = corpus.display_words(built_listing())
    image = image_words(address)
    mtb, nnn = address["mtb"], address["nnn"]
    obj = unit.objects
    sym = lambda name: address[obj[name].sym]
    failed = 0
    for n, routine in enumerate(ROUTINES):
        rng = random.Random(0o5000 + n)
        states = random_states(rng, RANDOM_CALLS, routine.ship, routine.cycles)
        base = states[0]
        for field, values in ((3, COUNTER_EDGES),) + routine.extra_edges:
            states += edges(base, field, values)
        watch = [(f"table {a:05o}", a, f"pdp1_table[0{a - mtb:o}]") for a in range(mtb, nnn)]
        watch += [("ran", address["ran"], "random_number"), ("mxc", sym("particles"), "particles"),
                  ("hpt", sym("angle_steps"), "angle_steps")]
        if routine.name == "explosion":
            msh = address[obj["spread_scale"].sym]
            watch += [("msh", msh, "word::bits(0100000 | pdp1_address(spread_scale))"),
                      ("mi1", sym("particle_shift"), "particle_shift")]
        senses = [s & 0o77 for s in (rng.randrange(1 << 6) for _ in states)]
        calls = [Inputs(k, rng.randrange(1 << 18), 0, senses[k]) for k in range(len(states))]
        entry = address[routine.sym] if routine.sym else address[unit.signatures[routine.name].sym]
        want = simh.run_jda(ROOT / "build/pdp1", ROOT / "build/oracle.rim", entry, calls,
                            watch=[a for _, a, _ in watch], op=routine.op, display=display,
                            each=[cursor_deposits(s, address, image) for s in states])
        got = reference.run(native(routine, unit, address, placed, states, [w for *_, w in watch]), calls)
        failed |= compare(f"{routine.name}", calls, want, got, [k for k, *_ in watch])
        print("  routine word after the call: " + outcomes(states, want, address, mtb))
    return failed


def outcomes(states: list[State], want, address: dict[str, int], mtb: int) -> str:
    """How often each calc routine ends up in the object's routine word: the
    branches the calls took."""
    names = {v: k for k, v in address.items()}
    seen = Counter()
    for s, w in zip(states, want):
        word = w.watched[s.slot]
        if word == s.words[0]:
            seen["unchanged"] += 1
        elif word == s.words[8]:
            seen["the saved routine"] += 1
        else:
            flag = " non-colliding" if word & 0o400000 else ""
            seen[(names.get(word & ir.ADDR_MASK, f"{word & ir.ADDR_MASK:05o}") if word else "0") + flag] += 1
    return ", ".join(f"{k} {n}" for k, n in seen.most_common())


if __name__ == "__main__":
    sys.exit(main())
