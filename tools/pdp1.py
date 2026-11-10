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
BUILD = ROOT / "build/runs"         # runsc's last build: its C and its listing
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
    ("outline_compiler", "start_over"): "ocm",
    ("outline_code", "stroke"): "nnn",
    ("central_star", "slope_x"): "bx", ("central_star", "slope_y"): "by",
    ("planetarium", "alternate_frames"): "bcc", ("planetarium", "window_steps"): "bkc",
    ("planetarium", "right_margin"): "fpr",
    ("star_catalog", "words"): "1j",
}

# A collection the binding lays out in pieces: (first slot, the symbol of its word).
PIECES = {("outlines", "codes"): [(0, "ot1"), (0o10, "ot2")]}

# Fields that hold a place in a collection: the binding keeps its address.
INTO = {("ships", "outline"): ("outline_code", "stroke"), ("outline_call", "code"): ("outline_code", "stroke"),
        ("magnitudes", "cursor"): ("star_catalog", "words"),
        ("outline_call", "table"): ("outlines", "codes"), ("outline_compiler", "table"): ("outlines", "codes")}

# The collection held as code (docs/rules/held-as-code.md): each slot is its
# member's words, laid out end to end. Fields held as a jump to one of its places.
CODE = ("outline_code", "stroke")
CODE_JUMPS = {("outline_compiler", "start_over"), ("outline_code", "back")}
JMP = 0o600000

# The PDP-1's words for the instructions of the code: memory reference
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


def template_members(prog: runs.Program) -> dict[str, list[tuple]]:
    """Each member of the collection held as code, as the words of its
    TEMPLATE, which runsc wrote and pdp1cc compiles, from the last build
    (build/runs): ("word", w), ("label", name), ("past", opcode, label)
    for a jump within it, ("hole", field) for a held field's word."""
    from pdp1cc import dialect, front
    from pdp1cc import program as cc
    _, files = cc.load(BUILD / "lift.toml")
    asts = [front.parse(f.c) for f in files]
    linked = dialect.external_symbols(asts)
    sym = cc.symbols((BUILD / "build/lift/program.lst").read_text(errors="replace"))
    prefix = "_".join(CODE) + "_"
    for f, ast in zip(files, asts):
        names = [e.decl.name for e in ast.ext if hasattr(e, "decl") and e.decl.name.startswith(prefix)]
        if names:
            dialect.lower_unit(ast, f.prefix, linked)
            break
    fields = {f"{r}_{n}": (r, n) for r, n in CODE_JUMPS}
    out = {}
    for name in sorted(set(names) & dialect._TEMPLATES.defs.keys()):
        items = []
        compiled = dialect._TEMPLATES.items(name, (), None)
        labels = {w.name for w in compiled if not hasattr(w, "op")}
        for w in compiled:
            if not hasattr(w, "op"):
                items.append(("label", w.name))
            elif w.rule == "HELD":
                items.append(("hole", fields[w.operand.name][1]))
            elif w.op == "jmp" and w.operand.name in labels:
                items.append(("past", JMP, w.operand.name))
            else:
                items.append(("word", word_value(w, sym)))
        out[name[len(prefix):]] = items
    return out


def word_value(w, sym: dict[str, int]) -> int:
    """The PDP-1 word of an instruction word pdp1cc selected."""
    o = w.operand
    if w.op in MEMORY:
        return MEMORY[w.op] << 12 | (0o10000 if w.i else 0) | sym[o.name] + o.offset
    if w.op == "iot" and w.i and o is None:
        return 0o730000                                     # ioh
    n = getattr(o, "n", getattr(o, "value", None))
    op, *rest = w.op.split()
    if rest:                                                # a skip spelled whole: `szf 5`
        n = int(rest[-1], 8)
    return {"stf": lambda: 0o760010 | n, "clf": lambda: 0o760000 | n, "szf": lambda: 0o640000 | n,
            "rcl": lambda: 0o663000 | (1 << n) - 1, "cma": lambda: 0o761000,
            "dpy-4000": lambda: DPY_NOWAIT}[op]()


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
        self.members = template_members(prog)
        self.code_slots: list[int] = []                 # the code laid out: each slot's address, then its end

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
        if (record, fld) in CODE_JUMPS:
            return JMP | self.code_address(value.v)
        if (record, fld) in INTO and INTO[(record, fld)] == CODE:
            return self.code_address(value.v)
        if (record, fld) in INTO and INTO[(record, fld)] in PIECES:
            return self.address(*INTO[(record, fld)], value.v)
        if (record, fld) in INTO:
            return (self.address(*INTO[(record, fld)], 0) + value.v) & runs.MASK
        return value.v

    def code_address(self, slot: int) -> int:
        """Where a slot of the code lies: in the code laid out, at its
        member's words; past it, a word a slot."""
        slots = self.code_slots or [self.address(*CODE, 0)]
        if slot < len(slots):
            return slots[slot]
        return (slots[-1] + slot - (len(slots) - 1)) & runs.MASK

    def code_slot(self, address: int) -> int:
        slots = self.code_slots or [self.address(*CODE, 0)]
        if address in slots:
            return slots.index(address)
        if slots[0] <= address < slots[-1]:
            raise ValueError(f"{address:o} is inside a stroke's words, not where one starts")
        return (address - slots[-1]) % (runs.MASK + 1) + len(slots) - 1

    def size(self, member: str) -> int:
        return sum(w[0] != "label" for w in self.members[member])

    def lay_out_code(self, code: dict, end: int) -> dict[int, int]:
        """The code's words for its slots before end, each its member's
        words (their templates), from the collection's address. Sets where
        each slot lies, for encode and decode."""
        fld = CODE[1]
        at = self.address(*CODE, 0)
        self.code_slots = []
        for k in range(end):
            self.code_slots.append(at)
            at += self.size(code[fld][k].name)
        self.code_slots.append(at)
        words = {}
        for k in range(end):
            words |= self.member_words(code[fld][k].name, self.code_slots[k],
                                       {h: code[h][k] for h in code if h != fld})
        return words

    def read_code(self, words: dict[int, int]) -> int:
        """SIMH's code read back as slots: from the collection's address, the
        member whose words lie there, one after another, while one does.
        Sets where each slot lies; returns the count of slots."""
        at = self.address(*CODE, 0)
        self.code_slots = [at]
        while True:
            for m in self.members:
                holes = {w[1]: None for w in self.members[m] if w[0] == "hole"}
                want = self.member_words(m, at, holes)
                if all(w is None or words.get(a) == w for a, w in want.items()):
                    break
            else:
                return len(self.code_slots) - 1
            at += self.size(m)
            self.code_slots.append(at)

    def member_words(self, member: str, at: int, holds: dict) -> dict[int, int | None]:
        """A member's words at an address. A jump to a place the slot holds
        is None when the place is not given."""
        ws = self.members[member]
        pos, k = {}, at
        for w in ws:
            if w[0] == "label":
                pos[w[1]] = k
            else:
                k += 1
        out, k = {}, at
        for w in ws:
            kind = w[0]
            if kind == "word":
                out[k] = w[1]
            elif kind == "past":
                out[k] = w[1] | pos[w[2]]
            elif kind == "hole":
                v = holds[w[1]]
                out[k] = None if v is None else JMP | self.code_address(v.v)
            if kind != "label":
                k += 1
        return out

    def decode(self, record: str, fld: str, word: int):
        typ = self.prog.records[record].fields[fld][0]
        if (record, fld) in CODE_JUMPS:
            return runs.W(self.code_slot(word & 0o7777))
        if (record, fld) in INTO and INTO[(record, fld)] == CODE:
            return runs.W(self.code_slot(word))
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
