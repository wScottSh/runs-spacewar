"""The PDP-1 binding of the Records: where each field lives in core and how
a value is spelled as a word. It is what a RUNS-to-PDP-1 compiler would
place by, and what the checks use to read Ground Truth's core as Records.

The binding holds only choices that play cannot observe. Where play reads
the layout, the RUNS text has to state it, and the binding follows the
text. tools/reach_oracle.py finds where play reaches the layout; so far it
finds no layout read that play observes (INTENT.md).

The addresses come from the oracle listing's symbol table, never from a
hard-coded number."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import runs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from oracle_check import oracle_symbols  # noqa: E402

SIMH = ROOT / "build/pdp1"
ORACLE = ROOT / "build/oracle.rim"

# Record field: the Macro symbol of its first word (a collection's array).
FIELDS = {
    ("objects", "routine"): "mtb", ("objects", "x"): "nx1", ("objects", "y"): "ny1",
    ("objects", "counter"): "na1", ("objects", "cycles"): "nb1",
    ("objects", "dx"): "ndx", ("objects", "dy"): "ndy",
    ("ships", "angular_momentum"): "nom", ("ships", "angle"): "nth", ("ships", "fuel"): "nfu",
    ("ships", "torpedoes"): "ntr", ("ships", "outline"): "not", ("ships", "previous_control"): "nco",
    ("ships", "saved_routine"): "nh1", ("ships", "jumps_left"): "nh2", ("ships", "recharge"): "nh3",
    ("ships", "uncertainty"): "nh4",
    ("random", "number"): "ran",
    ("frame", "spare_time"): "mtc", ("frame", "restart_delay"): "ntd", ("frame", "objects_seen"): "moc",
    ("score", "first"): "1sc", ("score", "second"): "2sc", ("score", "games_left"): "gct",
    ("controls", "source"): "cwg",
    ("tunables", "fuel_supply"): "foo", ("tunables", "angular_acceleration"): "maa",
    ("tunables", "star_capture_radius"): "str",
    ("tunables", "collision_radius"): "me1", ("tunables", "collision_radius_half"): "me2",
    ("tunables", "separate_outlines"): "ddd", ("tunables", "hyperspatial_uncertainty"): "hur",
    ("explosion_cloud", "particles"): "mxc",
    ("square_root_call", "entry"): "sqt", ("square_root_call", "passes_left"): "sq1",
    ("square_root_call", "root"): "sq2",
    ("multiply_call", "entry"): "mpy", ("multiply_call", "partial"): "mp2",
    ("integer_multiply_call", "entry"): "imp",
    ("divide_call", "high"): "dvd", ("divide_call", "quotient"): "idv",
    ("sine_call", "x"): "sin", ("sine_call", "answer"): "cos",
    ("spaceship", "controls"): "scw", ("spaceship", "sine"): "sn", ("spaceship", "cosine"): "cs",
    ("spaceship", "gravity_x"): "bx", ("spaceship", "gravity_y"): "by",
    ("spaceship", "operand"): "t1", ("spaceship", "x_squared"): "t2",
    ("spaceship", "nose_step_x"): "ssn", ("spaceship", "nose_step_y"): "scn",
    ("spaceship", "nose_x"): "sx1", ("spaceship", "nose_y"): "sy1", ("spaceship", "star_wait"): "ssn",
    ("spaceship", "torpedo_x"): "stx", ("spaceship", "torpedo_y"): "sty", ("spaceship", "flame"): "src",
    ("pen", "x"): "sx1", ("pen", "y"): "sy1", ("pen", "down_x"): "ssn", ("pen", "down_y"): "scn",
    ("pen", "out_x"): "scm", ("pen", "out_y"): "ssm", ("pen", "out_down_x"): "ssc",
    ("pen", "out_down_y"): "csm", ("pen", "in_down_x"): "csn", ("pen", "in_down_y"): "ssd",
    ("pen", "saved_x"): "ssa", ("pen", "saved_y"): "ssi",
    ("outline_compiler", "codes_left"): "occ", ("outline_compiler", "codes_rest"): "oci",
    ("outline_compiler", "start_over"): "ocm", ("outline_compiler", "to_other_side"): "ocn",
    ("outline_code", "insn"): "nnn",
    ("central_star", "slope_x"): "bx", ("central_star", "slope_y"): "by",
    ("planetarium", "alternate_frames"): "bcc", ("planetarium", "window_steps"): "bkc",
    ("planetarium", "right_margin"): "fpr",
    ("star_catalog", "words"): "1j",
}

# A collection the binding lays out in pieces: (first slot, the symbol of its word).
PIECES = {("outlines", "codes"): [(0, "ot1"), (0o10, "ot2")]}

# Fields that hold a place in a collection: the binding keeps its address.
INTO = {("ships", "outline"): ("outline_code", "insn"), ("outline_call", "code"): ("outline_code", "insn"),
        ("magnitudes", "cursor"): ("star_catalog", "words"),
        ("outline_call", "table"): ("outlines", "codes"), ("outline_compiler", "table"): ("outlines", "codes")}

# The PDP-1's words for the instructions of `type insn`: memory reference
# instructions are an operation and an address, the rest whole words.
MEMORY = {"lac": 0o20, "lio": 0o22, "dac": 0o24, "dio": 0o32, "add": 0o40, "sub": 0o42, "jmp": 0o60}
# The routines code jumps to: the label of each.
ROUTINES = {"after_outline": "sq6"}

# Fields the original keeps inside an instruction, not in a word of their
# own: the value is the shift count of the instruction at that label, which
# the program builds or sets and then executes. explosion_cloud.spread picks
# mst's scr 1s or scr 3s (dap msh); explosion_cloud.scatter is the count of
# the scl the program writes whole at mi1. handoff has no place in core: its
# fields are AC and IO between two instructions.
INSTRUCTION_FIELDS = {("explosion_cloud", "spread"): "msh", ("explosion_cloud", "scatter"): "mi1",
                      ("launch", "slot"): "sr1", ("outline_compiler", "table"): "ocg"}

# calc_routine: the routine's entry, and the sign bit when it does not collide.
ROUTINE_WORDS = {"none": None, "first_spaceship": "ss1", "second_spaceship": "ss2",
                 "torpedo": "tcr", "explosion": "-mex", "in_hyperspace": "-hp1", "breakout": "hp3"}
# Each enum stored in core: its members' words, as routine addresses.
ENUM_WORDS = {"calc_routine": ROUTINE_WORDS,
              "control_source": {"test_word": "mg2", "control_boxes": "cwr"}}

# The devices, as the binding states them in one place (pdp1/devices.toml):
# the sense switch of each console field, the start address of each top
# Network.
DEVICES = tomllib.loads((ROOT / "pdp1/devices.toml").read_text())
SWITCHES = {f.split(".")[1]: how["sense"] for f, how in DEVICES["console"].items()
            if isinstance(how, dict) and "sense" in how}
START = {v["at"]: v["network"] for v in DEVICES["start"]}

# Fields the PDP-1 keeps in its program flags, an enum's first member
# clear and its second set: the lights (devices.toml) and each binding's
# [flags]. SIMH's PF holds flag n as bit 1 << (6 - n).
FLAGS = {tuple(f.split(".")): n for f, n in DEVICES["lights"].items()} | {
    tuple(f.split(".")): n for b in sorted((ROOT / "pdp1").glob("*.toml"))
    for f, n in tomllib.loads(b.read_text()).get("flags", {}).items()}

# The Expensive Planetarium lays out each magnitude's words in its code
# (dislis: fpo, flo), with no symbol of their own: each instance of the
# macro begins `clf 5 / lac flo / dap fpo / dap fin / dap fyn`. The words
# per magnitude: its scan start, cursor, and the homes of star_x and star_y.
DISLIS = 0o760005


def magnitude_words(sym: dict, image: dict[int, int]) -> list[dict[str, int]]:
    starts = [a for a in range(sym["bck"], sym["bcc"]) if image.get(a) == DISLIS]
    return [{name: image[a + k] & 0o7777 for k, name in ((1, "cursor"), (2, "scan_start"), (3, "star_x"),
                                                          (4, "star_y"))} for a in starts]

DPY = 0o720007              # dpy, intensity in bits 6-8
DPY_NOWAIT = 0o724007


class Binding:
    def __init__(self, prog: runs.Program):
        self.prog = prog
        self.sym = oracle_symbols()
        self.enum_word = {enum: {name: 0 if s is None else
                                 (self.sym[s.lstrip("-")] | (runs.SIGN if s.startswith("-") else 0))
                                 for name, s in words.items()}
                          for enum, words in ENUM_WORDS.items()}
        self.enum_of = {enum: {w: n for n, w in words.items()} for enum, words in self.enum_word.items()}
        self.routine_word = self.enum_word["calc_routine"]
        self.moved: dict[tuple[str, str], int] = {}     # a field a check lays out elsewhere: its address
        self.slot_at: dict[tuple[str, str, int], int] = {}  # a slot laid out on its own: its address

    def address(self, record: str, fld: str, slot: int | None = None) -> int:
        if (record, fld, slot) in self.slot_at:
            return self.slot_at[(record, fld, slot)]
        if (record, fld) in self.moved:
            return self.moved[(record, fld)] + (slot or 0)
        if (record, fld) in PIECES:
            first, name = next((f, n) for f, n in reversed(PIECES[(record, fld)]) if f <= slot)
            return self.sym[name] + slot - first
        return self.sym[FIELDS[(record, fld)]] + (slot or 0)

    def encode(self, record: str, fld: str, value) -> int:
        if isinstance(value, runs.Member):
            return self.enum_word[value.enum][value.name]
        if isinstance(value, runs.Insn):
            return self.instruction(value)
        if (record, fld) in INTO and INTO[(record, fld)] in PIECES:
            return self.address(*INTO[(record, fld)], value.v)
        if (record, fld) in INTO:
            return (self.address(*INTO[(record, fld)], 0) + value.v) & runs.MASK
        return value.v

    def instruction(self, i: runs.Insn) -> int:
        """The word the PDP-1 runs for an instruction of the RUNS text."""
        x = i.operand
        if i.op in MEMORY:
            where = self.sym[ROUTINES[x]] if isinstance(x, str) else self.address(x.record, x.field, x.slot)
            return MEMORY[i.op] << 12 | where
        return {"stf": lambda: 0o760010 | x, "clf": lambda: 0o760000 | x, "szf": lambda: 0o640000 | x,
                "rcl": lambda: 0o663000 | (1 << x) - 1, "cma": lambda: 0o761000, "ioh": lambda: 0o730000,
                "dpy": lambda: DPY_NOWAIT}[i.op]()

    def decode(self, record: str, fld: str, word: int):
        typ = self.prog.records[record].fields[fld][0]
        if (record, fld) in INTO:
            if INTO[(record, fld)] in PIECES:
                raise ValueError(f"{record}.{fld}: no place in a collection laid out in pieces is read back")
            return runs.W((word - self.address(*INTO[(record, fld)], 0)) % (runs.MASK + 1))
        if typ in self.enum_of:
            if word not in self.enum_of[typ]:
                raise ValueError(f"{record}.{fld}: {word:06o} is no {typ}")
            return runs.Member(typ, self.enum_of[typ][word])
        return runs.W(word)

    def flag_members(self, rec: str, fld: str) -> list[str]:
        return self.prog.enums[self.prog.records[rec].fields[fld][0]]

    def flags_word(self, state: dict) -> int:
        """The program flags that hold fields of the given Records, as SIMH's PF."""
        return sum(1 << (6 - n) for (rec, fld), n in FLAGS.items()
                   if rec in state and state[rec][fld].name == self.flag_members(rec, fld)[1])

    def read_flags(self, pf: int, records=("lights",)) -> dict:
        out: dict = {}
        for (rec, fld), n in FLAGS.items():
            if rec in records:
                enum = self.prog.records[rec].fields[fld][0]
                out.setdefault(rec, {})[fld] = runs.Member(enum, self.prog.enums[enum][pf >> (6 - n) & 1])
        return out

    def places(self, records: list[str]):
        """Every (record, field, slot, address) of the named Records; fields
        held in a program flag or an instruction are not words of their own."""
        for rec in records:
            r = self.prog.records[rec]
            for fld in r.fields:
                if (rec, fld) in FLAGS or (rec, fld) in INSTRUCTION_FIELDS:
                    continue
                for slot in (range(r.count) if r.count else [None]):
                    yield rec, fld, slot, self.address(rec, fld, slot)

    def share_one_word(self, state: dict, records: list[str]):
        """Give the names that share a word one value: the first's."""
        first = {}
        for rec, fld, slot, at in self.places(records):
            if slot is None and isinstance(state[rec][fld], runs.W):
                state[rec][fld] = first.setdefault(at, state[rec][fld])

    def outlived(self, m: runs.Machine, records: list[str], since: int) -> set[tuple[str, str]]:
        """The names whose word another name wrote after them, since a
        point in m's writes: the word no longer holds them."""
        last = lambda rf: max(m.written.get(rf, 0), since)
        by_word = {}
        for rec, fld, slot, at in self.places(records):
            if slot is None:
                by_word.setdefault(at, []).append((rec, fld))
        return {rf for names in by_word.values() for rf in names
                if any(last(other) > last(rf) for other in names)}

    def deposits(self, state: dict, records: list[str]) -> dict[int, int]:
        out = {}
        for rec, fld, slot, at in self.places(records):
            v = state[rec][fld] if slot is None else state[rec][fld][slot]
            out[at] = self.encode(rec, fld, v)
        return out

    def read(self, words: dict[int, int], records: list[str]) -> dict:
        out = {}
        for rec, fld, slot, at in self.places(records):
            v = self.decode(rec, fld, words[at])
            if slot is None:
                out.setdefault(rec, {})[fld] = v
            else:
                out.setdefault(rec, {}).setdefault(fld, [None] * self.prog.records[rec].count)[slot] = v
        return out


def point(plotted: tuple[int, int, int]) -> tuple:
    """A plotted point as the display stream holds it: x, y, intensity."""
    insn, x, y = plotted
    if insn == DPY_NOWAIT:              # plots at intensity 0, and asks for a completion pulse
        return (runs.W(x), runs.W(y), 0)
    if insn & ~0o700 != DPY:
        raise ValueError(f"{insn:06o} is not a display instruction")
    return (runs.W(x), runs.W(y), (insn >> 6) & 7)
