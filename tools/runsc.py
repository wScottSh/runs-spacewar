"""runsc: RUNS and its PDP-1 binding -> the pdp1c C dialect -> pdp1cc -> the
tape image, compared by sha256 with the original's.

The RUNS text holds the game. The binding (pdp1/<unit>.toml) holds only how
the PDP-1 carries it: the order of things on the tape, each routine's
calling convention, which register or word holds a value, and how a
routine's code is laid out. pdp1cc, the lift's compiler, is the back end.

A bound routine is one C function. A Processor's body is its code. A
Network's Processors are inlined in the order it runs them, under its
guards and loops, and each `run` of another bound routine is a call: the
sets of that routine's parameter fields just before the run become the
call's arguments, and its result fields read after the run are AC, or the
halves of the returned pair. A macro is a routine laid out at each run.

Every unit of the lift's lift.toml has a binding and is compiled from
RUNS: the C this writes stands alone, with no file of lift/."""
from __future__ import annotations

import contextlib
import io
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import runs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.pdp1cc import dialect, front, program, select  # noqa: E402

# The program to compile: a directory with its RUNS text (runs/), its binding
# (pdp1/) and its lift.toml. RUNS_PROGRAM names another (programs/minskytron);
# the default is Spacewar, at the root.
PROGRAM = runs.program_dir()
BINDINGS = PROGRAM / "pdp1"
DEVICES = "devices.toml"                   # in BINDINGS: the presentation side of the boundary
OUT = ROOT / "build/runs" if PROGRAM == ROOT else ROOT / "build" / PROGRAM.name

# C precedence, loosest first, for the operators RUNS shares with C.
C_LEVEL = {"or": 1, "and": 2, "|": 3, "^": 4, "&": 5, "==": 6, "!=": 6,
           "<": 7, "<=": 7, ">": 7, ">=": 7, "<<": 8, ">>": 8, "+": 9, "-": 9, "*": 10, "/": 10}
C_OP = {"or": "||", "and": "&&"}
NEGATED = {"<": ">=", ">=": "<", ">": "<=", "<=": ">", "==": "!=", "!=": "=="}
PAIR_OPS = {"rcl", "rcr", "scl", "scr", "mus", "dis"}
IO_ROTATE = {"ral": "ril", "rar": "rir"}
RETURNS = {0: "void", 1: "word", 2: "dword"}


class BindError(Exception):
    pass


class Section(dict):
    """A part of the bindings: a key it lacks, which the RUNS needs, is a
    BindError that says what is missing."""

    def __init__(self, what: str, *args):
        super().__init__(*args)
        self.what = what

    def __missing__(self, key):
        raise BindError(f"no binding gives {self.what} {key!r}")


def octal(n: int) -> str:
    return f"0{n:o}" if n > 7 else str(n)


def leaf(dotted: str) -> str:
    return dotted.split(".")[1]


def dotted_of(e) -> str | None:
    """`record.field` for a field expression, else None."""
    if e[0] == "field" and e[1][0] == "name":
        return f"{e[1][1]}.{e[2]}"
    return None


def held_field(e) -> str | None:
    """The field a plain read or write names: `record.field`, or a slot of it."""
    if not isinstance(e, tuple) or not e:
        return None
    return dotted_of(e[1]) if e[0] == "index" else dotted_of(e)


def as_field(dotted: str):
    return ("field", ("name", dotted.split(".")[0]), leaf(dotted))


def walk(stmts: list):
    """Every statement, nested ones included."""
    for s in stmts:
        yield s
        if s[0] == "if":
            for _, body in s[1]:
                yield from walk(body)
            yield from walk(s[2])
        elif s[0] in ("loop", "for", "slots"):
            yield from walk(s[-2])


def walk_expr(e):
    """Every node of an expression."""
    if isinstance(e, tuple) and e and isinstance(e[0], str):
        yield e
        for x in e[1:]:
            if isinstance(x, (tuple, list)):
                yield from walk_expr(x)
    elif isinstance(e, list):
        for x in e:
            yield from walk_expr(x)


def substitute(tree, names: dict):
    """tree with each ("name", n) for n in names replaced by names[n]."""
    if isinstance(tree, tuple) and len(tree) == 2 and tree[0] == "name" and tree[1] in names:
        return names[tree[1]]
    if isinstance(tree, list):
        return [substitute(t, names) for t in tree]
    if isinstance(tree, tuple):
        return tuple(substitute(t, names) for t in tree)
    if isinstance(tree, dict):
        return {k: substitute(v, names) for k, v in tree.items()}
    return tree


def mark_homes(tree, fields: set[str]):
    """tree with each slot of one of fields marked as where its cursor may
    have its home: ("index", field, slot, "home")."""
    if isinstance(tree, tuple) and len(tree) == 3 and tree[0] == "index" and dotted_of(tree[1]) in fields:
        return (*tree, "home")
    if isinstance(tree, list):
        return [mark_homes(t, fields) for t in tree]
    if isinstance(tree, tuple):
        return tuple(mark_homes(t, fields) for t in tree)
    return tree


def returns_to(stmts: list, label: str) -> list:
    """stmts with each return a jump to label."""
    out = []
    for s in stmts:
        if s[0] == "return":
            out.append(("goto", label, s[-1]))
        elif s[0] == "if":
            out.append(("if", [(c, returns_to(b, label)) for c, b in s[1]], returns_to(s[2], label), s[3]))
        elif s[0] in ("loop", "for"):
            out.append((*s[:-2], returns_to(s[-2], label), s[-1]))
        else:
            out.append(s)
    return out


def has_return(tree) -> bool:
    if isinstance(tree, tuple) and tree and tree[0] == "return":
        return True
    return isinstance(tree, (list, tuple, dict)) and any(
        has_return(t) for t in (tree.values() if isinstance(tree, dict) else tree))


def breaks(stmts: list) -> bool:
    """A break of this loop: one not inside a loop of its own."""
    for s in stmts:
        if s[0] == "break" or s[0] == "if" and any(breaks(b) for b in [b for _, b in s[1]] + [s[2]]):
            return True
    return False


def falls_off(stmts: list) -> bool:
    """Control can run past the last statement."""
    if not stmts:
        return True
    s = stmts[-1]
    return not (s[0] == "return" or s[0] == "loop" and not breaks(s[2]))


def field_type(prog: runs.Program, e) -> str | None:
    """The type a field expression's word holds, or None."""
    d = dotted_of(e[1] if e[0] == "index" else e) if e[0] in ("field", "index") else None
    if d is None or d.split(".")[0] not in prog.records:
        return None
    rec, fld = d.split(".")
    return prog.records[rec].fields.get(fld, (None,))[0]


def resolve(prog: runs.Program, name: str, enum: str | None, where: str) -> str:
    """The enum a member's name means: the enum of the field it is stored
    in or compared with, as the evaluator types it; else the one enum that
    has the name."""
    if enum in prog.enums:
        if name not in prog.enums[enum]:
            raise BindError(f"{where}: {name} is no member of {enum}")
        return enum
    owners = [e for e, ms in prog.enums.items() if name in ms]
    if len(owners) != 1:
        raise BindError(f"{where}: {name} is a member of {owners}: say which by the field it is stored in or "
                        f"compared with")
    return owners[0]


def typed(prog: runs.Program, tree, local_names: set[str], where: str = ""):
    """tree with each member's name ("name", m) as ("member", enum, m),
    the enum the evaluator gives it where it stands (resolve). A local's
    enum is the one every member set into it shares."""
    locals_enum: dict[str, set[str]] = {}
    for s in walk(tree if isinstance(tree, list) else []):
        if s[0] in ("let", "set") and s[1][0] == "name" and s[2][0] == "name" and s[2][1] not in local_names:
            have = {e for e, ms in prog.enums.items() if s[2][1] in ms}
            locals_enum[s[1][1]] = locals_enum.get(s[1][1], have) & have

    def enum_of(e) -> str | None:
        if e[0] == "name" and e[1] in local_names:
            have = locals_enum.get(e[1], set())
            return next(iter(have)) if len(have) == 1 else None
        typ = field_type(prog, e)
        return typ if typ in prog.enums else None

    def is_member(e) -> bool:
        return isinstance(e, tuple) and len(e) == 2 and e[0] == "name" and isinstance(e[1], str) \
            and e[1] not in local_names and any(e[1] in ms for ms in prog.enums.values())

    def go(x, context: str | None, at: str):
        if is_member(x):
            return ("member", resolve(prog, x[1], context, at), x[1])
        if isinstance(x, list):
            return [go(y, None, at) for y in x]
        if not isinstance(x, tuple) or not x:
            return x
        at = x[-1] if isinstance(x[-1], str) and x[0] in ("let", "set", "if", "loop", "for", "run", "emit",
                                                          "match", "return", "jump") else at
        if x[0] in ("let", "set"):
            return (x[0], go(x[1], None, at), go(x[2], enum_of(x[1]), at), x[3])
        if x[0] == "bin" and x[1] in ("==", "!="):
            return ("bin", x[1], go(x[2], enum_of(x[3]), at), go(x[3], enum_of(x[2]), at))
        if x[0] == "match":
            return ("match", go(x[1], None, at), {m: go(b, None, at) for m, b in x[2].items()}, x[3])
        return tuple(go(y, None, at) if isinstance(y, (tuple, list)) else y for y in x)
    return go(tree, None, where)


def table_cases(s):
    """An if-chain with no else whose every guard tests one value for
    `== n`, or an `or` of such tests, the numbers 0 to some n, each once:
    (the value, [(the arm's numbers, the arm's body)]), else None."""
    if s[0] != "if" or s[2] or len(s[1]) < 3:
        return None
    value, arms = None, []
    for c, body in s[1]:
        numbers, stack = [], [c]
        while stack:
            t = stack.pop()
            if t[0] == "bin" and t[1] == "or":
                stack += [t[3], t[2]]
                continue
            if not (t[0] == "bin" and t[1] == "==" and t[3][0] == "num" and t[2] == (value or t[2])):
                return None
            value = t[2]
            numbers.append(t[3][1])
        arms.append((numbers, body))
    if sorted(n for numbers, _ in arms for n in numbers) != list(range(sum(len(ns) for ns, _ in arms))):
        return None
    return value, arms


# The names C and the dialect's header (pdp1.h) already give meaning to.
C_WORDS = set(re.findall(r"[A-Za-z_]\w*", (ROOT / "tools/pdp1cc/include/pdp1.h").read_text())) | {
    "auto", "break", "case", "char", "const", "continue", "default", "do", "double", "else", "enum", "extern",
    "float", "for", "goto", "if", "inline", "int", "long", "register", "return", "short", "signed", "sizeof",
    "static", "struct", "switch", "typedef", "union", "unsigned", "void", "volatile", "while"}


@dataclass
class Walk:
    """A walker over a collection held as a run of code: from a slot, take
    each slot's member and run its arm, then go on to the next slot.
    The use of the collection's field is the dispatch: each member's code
    is its arm, and stepping on is falling into the next slot's code."""
    routine: str
    start: tuple                # the slot it starts from (an expression)
    field: str                  # the collection's field, held as code
    at: str                     # the local that holds the slot
    arms: dict                  # member -> its arm's statements, as a template runs them
    jumps: list                 # held fields the walk goes on from (`set at = L.f[at]; continue`)
    holds: dict                 # member -> those fields its arm holds, in order
    where: str

    @staticmethod
    def of(prog: runs.Program, r: runs.Routine, held: set[str]) -> "Walk":
        where = r.body[0][-1] if r.body else r.name
        shape = (f"{where}: {r.name} walks a collection held as code: `let at = <slot>`, then a loop of "
                 f"`let m = L.f[at]`, an if-chain on `m == <member>`, and `set at = at + 1`")
        if len(r.body) != 2 or r.body[0][0] != "let" or r.body[0][1][0] != "name" or r.body[1][0] != "loop":
            raise BindError(shape)
        at, start = r.body[0][1][1], r.body[0][2]
        inner = r.body[1][-2]
        if len(inner) != 3 or inner[0][0] != "let" or inner[1][0] != "if" or inner[1][2] \
                or inner[2][:3] != ("set", ("name", at), ("bin", "+", ("name", at), ("num", 1))):
            raise BindError(shape)
        take = inner[0]
        if take[1][0] != "name" or take[2][0] != "index" or take[2][2] != ("name", at):
            raise BindError(shape)
        m, field = take[1][1], held_field(take[2])
        if field not in held:
            raise BindError(f"{where}: {r.name} walks {field}, which is not held as code (held_as_code)")
        arms, holds, jumps = {}, {}, []

        def arm(stmts: list, member: str) -> list:
            out, k = [], 0
            while k < len(stmts):
                s = stmts[k]
                if s[0] == "set" and s[1] == ("name", at):
                    g = held_field(s[2]) if s[2][0] == "index" and s[2][2] == ("name", at) else None
                    if g not in held or k + 1 >= len(stmts) or stmts[k + 1][0] != "continue":
                        raise BindError(f"{s[-1]}: the walk goes on only to the next slot, or from a held "
                                        f"place: `set {at} = L.f[{at}]` then continue, with L.f held as code")
                    out.append(("held_jump", g, s[-1]))
                    holds[member].append(g)
                    jumps.append(g) if g not in jumps else None
                    k += 2
                    continue
                if s[0] == "break":
                    out.append(("leave", s[-1]))
                elif s[0] == "if":
                    out.append(("if", [(g, arm(b, member)) for g, b in s[1]], arm(s[2], member), s[-1]))
                elif runs.mentions(s, {at, m}) or s[0] == "continue":
                    raise BindError(f"{s[-1]}: an arm of the walk reads neither the slot nor the member")
                else:
                    out.append(s)
                k += 1
            return out

        for guard, body in inner[1][1]:
            if not (guard[0] == "bin" and guard[1] == "==" and guard[2] == ("name", m) and guard[3][0] == "name"):
                raise BindError(shape)
            holds[guard[3][1]] = []
            arms[guard[3][1]] = arm(body, guard[3][1])
        return Walk(r.name, start, field, at, arms, jumps, holds, where)

    def registers(self, binds: "Bindings") -> list[str]:
        """The register fields the arms use: what AC and IO hold as the walk runs."""
        found = {dotted_of(e) for s in self.arms.values() for e in walk_expr(s) if e[0] == "field"}
        return sorted(f for f in found if f and f.split(".")[0] in binds.registers)


@dataclass(frozen=True)
class RunCode:
    """What pdp1cc's words for the members of a collection held as a run of
    code say about storing them (pdp1cc dialect.template_words)."""
    jumps: bool         # a member's code jumps within itself: the jump is built in a data word
    stored: int         # how many times one call of the store routine stores IO; 0: no store routine here


@dataclass
class Bound:
    """One bound routine: how the PDP-1 enters and leaves it."""
    name: str
    unit: Path
    convention: str
    entry: str | None = None            # JDA: the entry word, which holds AC on entry
    ac_param: str | None = None         # arrives in AC, with no entry word (XCT)
    io_param: str | None = None         # arrives in IO
    byname: str | None = None           # the word after the call, executed each time it is read
    result: list[str] = field(default_factory=list)     # AC, then IO
    block: str | None = None            # the body lies in a BLOCK that others jump into
    block_takes_entry: bool = False     # the block is entered with the entry word in AC
    skips: tuple[str, str] | None = None    # (field, member): return one word further when it holds member
    io: set[str] = field(default_factory=set)       # locals and fields that live in IO
    cells: list[str] = field(default_factory=list)  # other fields that live in the entry word
    loops: str | None = None            # "exit first": see Function.loop
    shifts: str | None = None           # "xct": each shift is executed from a constant word
    pool: set[str] = field(default_factory=set)     # locals that live in a pool word
    spill: set[str] = field(default_factory=set)    # AC locals kept in a pool word from their last set on
    inline: str | None = None           # a constant word after the call (INLINE)
    pointers: set[str] = field(default_factory=set)     # fields that hold addresses (word *)
    io_reads: set[str] = field(default_factory=set)     # fields a guard reads into IO, AC being busy
    back: str | None = None             # code a Record holds: the routine it jumps back to
    pulse: bool = False                 # that code waits for a display completion pulse
    code: bool = False                  # a Processor whose body jumps into code a Record holds
    args_done: str | None = None        # the Processor after which the routine steps past its inline words
    data: list[str] = field(default_factory=list)       # data words laid out inside the routine
    flags: dict[str, int] = field(default_factory=dict)     # locals held in a program flag
    homes: dict[str, str] = field(default_factory=dict)     # locals held in an instruction's address field
    into: dict[str, str] = field(default_factory=dict)      # locals that hold a place in a collection
    arms: str | None = None             # "apart": see Function.apart_loop
    exit_after: str | None = None       # the exit lies in the guard after this Processor: see Function.guards
    returns_shift: bool = False         # its AC result holds a shift instruction (Unit.copied_kinds)
    tails: str | None = None            # "shared": paths that join share the words they end with (SHARED_TAILS)

    def typed(self, dotted: str, name: str) -> str:
        return f"word *{name}" if dotted in self.pointers else f"word {name}"

    def params(self, block: bool = False) -> list[tuple[str, str]]:
        """(field, C declaration) in the dialect's order: AC, IO, by name."""
        out = []
        if self.entry and (not block or self.block_takes_entry):
            out.append((self.entry, self.typed(self.entry, leaf(self.entry))))
        if self.ac_param:
            out.append((self.ac_param, f"word {leaf(self.ac_param)}"))
        if self.io_param:
            out.append((self.io_param, f"register word {leaf(self.io_param)}"))
        if self.byname:
            out.append((self.byname, f"BYNAME word {leaf(self.byname)}"))
        if self.inline:
            const = "const " if self.inline in self.pointers else ""
            out.append((self.inline, f"INLINE {const}{self.typed(self.inline, leaf(self.inline))}"))
        return out

    def returns(self) -> str:
        if self.returns_shift:
            return "shift" if len(self.result) == 1 else "shift_pair"
        if len(self.result) == 1 and self.result[0] in self.pointers:
            return "word *"
        if len(self.result) == 1 and self.result[0] in self.io and self.convention == "JSP":
            return "io_word"
        return RETURNS[len(self.result)]

    def declaration(self, block: bool = False, definition: bool = False) -> str:
        conv = "BLOCK" if block else self.convention
        conv += " SHARED_TAILS" if definition and not block and self.tails == "shared" else ""
        conv = "static inline" if conv == "INLINE" else conv
        skips = " SKIPS" if self.skips else ""
        params = ", ".join(d for _, d in self.params(block)) or "void"
        ret = self.returns()
        return f"{conv}{skips} {ret}{'' if ret.endswith('*') else ' '}{self.block if block else self.name}({params})"


def _name(v) -> bool:
    return isinstance(v, str) and re.fullmatch(r"[A-Za-z_]\w*", v) is not None


def _field(v) -> bool:
    return isinstance(v, str) and re.fullmatch(r"[A-Za-z_]\w*\.[A-Za-z_]\w*", v) is not None


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _list(item, n: int | None = None):
    return lambda v: isinstance(v, list) and all(item(x) for x in v) and (n is None or len(v) == n)


def _dict(key, value):
    return lambda v: isinstance(v, dict) and all(key(k) and value(x) for k, x in v.items())


def _one_of(*words):
    return lambda v: isinstance(v, str) and v in words


def _either(*kinds):
    return lambda v: any(k(v) for k in kinds)


_BOOL = lambda v: isinstance(v, bool)               # noqa: E731
_TRUE = lambda v: v is True                         # noqa: E731
_TEXT = lambda v: isinstance(v, str)                # noqa: E731
_LOCAL = _either(_name, _field)
_SPELLED = _either(_int, _dict(_one_of("routine", "sign", "literal"), _either(_name, _BOOL)))
_DEVICE = _either(_name, _dict(_one_of("read", "or_into_io", "sense"), _either(_name, _BOOL, _int)))
_SECTION = lambda v: isinstance(v, dict)            # noqa: E731
_PLACES = _list(_SECTION)

# The keys a binding may hold, by where they stand, and the kind of value
# each takes: a field (record.field), a name (a routine, a local, a C word),
# a number, a flag, or one of a few words.
SCHEMA = {
    "unit": {"replaces": _TEXT, "registers": _list(_name), "pool": _list(_field), "repeat": _name,
             "moves": _one_of("swap"), "place": _PLACES, "inline": _PLACES, "code": _PLACES,
             "share": _dict(_field, _field), "into": _dict(_field, _field),
             "spell": _dict(_name, _dict(_name, _SPELLED)), "flags": _dict(_field, _int),
             "homes": _dict(_field, _one_of("table", "pointer")), "held_as_code": _list(_field),
             "code_words": _dict(_field, _int),
             "addresses": _dict(_field, _one_of("after table")), "table": _SECTION,
             "cursors": _dict(_field, _either(_name, _dict(_field, _name))), "walk": _SECTION,
             "streams": _dict(_name, _one_of("dpy", "hlt"))},
    "devices": {"console": _dict(_field, _DEVICE), "lights": _dict(_field, _int), "start": _PLACES},
    "start": {"at": _int, "network": _name, "tape": _BOOL},
    "walk": {"set_after": _name, "index": _field, "homes": _list(_field), "home_in": _dict(_field, _name),
             "carry": _list(_name), "stray": _SECTION, "other": _dict(_field, _name)},
    "stray": {"after": _field, "cursor": _name},
    "table": {"at": _name, "records": _list(_name), "clear": _name},
    "routine": {"routine": _name, "convention": _one_of("JDA", "JSP", "XCT", "BLOCK"), "entry": _field,
                "ac_param": _field, "io_param": _field, "byname": _field, "result": _list(_field),
                "io": _list(_LOCAL), "cells": _list(_field), "skips": lambda v: _list(_TEXT, 2)(v) and _field(v[0]) and _name(v[1]),
                "block": _name, "block_takes_entry": _BOOL, "loops": _one_of("exit first"),
                "shifts": _one_of("xct"), "pool": _list(_LOCAL), "spill": _list(_name), "inline": _field,
                "io_reads": _list(_field), "args_done": _name, "data": _list(_LOCAL),
                "flags": _dict(_name, _int), "homes": _dict(_name, _one_of("pointer")),
                "into": _dict(_name, _field), "arms": _one_of("apart"), "exit_after": _name, "pulse": _BOOL,
                "tails": _one_of("shared")},
    "inline": {"routine": _name, "ac_param": _field, "result": _list(_field), "shifts": _one_of("xct")},
    "code": {"routine": _name, "pulse": _BOOL, "io": _list(_LOCAL)},
    "store": {"store": _field, "loaded": _name},
    "fields": {"fields": _list(_field)},
    "slots": {"slots": _field, "range": _list(_int, 2), "reserve": _int},
    "machine": {"machine": _one_of("constants", "variables", "patch space", "sequence break",
                                   "sequence break flush", "start vectors"), "reserve": _int},
    "jsp_slot": {"jsp_slot": _name, "at": _int, "returns": _one_of("io", "ac"), "jump": _name, "reserve": _int},
    "exit": {"exit": _name},
    "table place": {"table": _TRUE},
    "shifts": {"shifts": _field},
    "base": {"base": _field},
}
# The keys each must hold.
REQUIRED = {"unit": {"replaces", "place"}, "routine": {"convention"}, "inline": {"routine"}, "code": {"routine"},
            "slots": {"range"}, "jsp_slot": {"at", "returns", "jump"}, "table": {"at", "records"},
            "store": {"loaded"},
            "stray": {"after", "cursor"}, "start": {"at", "network"}}


def check_keys(path: Path, d, kind: str, where: str):
    """Each key is one runsc knows where it stands, with a value of its kind."""
    if not isinstance(d, dict):
        raise BindError(f"{path.name}: {where} is a table of keys")
    if unknown := set(d) - set(SCHEMA[kind]):
        raise BindError(f"{path.name}: {where}: unknown keys {sorted(unknown)}")
    if missing := REQUIRED.get(kind, set()) - set(d):
        raise BindError(f"{path.name}: {where}: missing {sorted(missing)}")
    for k, v in d.items():
        if not SCHEMA[kind][k](v):
            raise BindError(f"{path.name}: {where}: {k} = {v!r} is not a value {k} takes")


def check_schema(path: Path, spec: dict):
    """Every key of a binding, its kind of value, and the keys it needs."""
    check_keys(path, spec, "unit", "the unit")
    check_keys(path, spec.get("walk", {}), "walk", "[walk]")
    if "stray" in spec.get("walk", {}):
        check_keys(path, spec["walk"]["stray"], "stray", "[walk] stray")
    if "table" in spec:
        check_keys(path, spec["table"], "table", "[table]")
    for section in ("place", "inline", "code"):
        for p in spec.get(section, []):
            kind = section if section != "place" else next(
                (k for k in ("routine", "fields", "slots", "machine", "jsp_slot", "exit") if k in p),
                "table place" if "table" in p else "shifts" if "shifts" in p else "base" if "base" in p
                else "store" if "store" in p else None)
            if kind is None:
                raise BindError(f"{path.name}: a place is a routine, fields, slots or a machine word: {p}")
            check_keys(path, p, kind, f"[[{section}]] {p.get(kind if kind in p else 'routine', '')}")


def routine_locals(r: runs.Routine) -> set[str]:
    """A routine's parameters, and every name its lets and counted loops bind."""
    out = set(r.params)
    for s in walk(r.body):
        if s[0] == "let":
            out |= {t[1] for t in (s[1][1] if s[1][0] == "tuple" else [s[1]]) if t[0] == "name"}
        elif s[0] == "for":
            out.add(s[1])
    return out


def own_routines(prog: runs.Program, name: str, bound: set[str]):
    """A bound routine and the routines it compiles inline."""
    yield name
    for inner in sorted(runs.runs_of(prog.routines[name].body) - bound):
        if inner in prog.routines:
            yield from own_routines(prog, inner, bound)


class Bindings:
    """Every binding in pdp1/: the routines they bind and where fields live."""

    def __init__(self, prog: runs.Program, paths: list[Path]):
        self.prog = prog
        self.specs = {p: tomllib.loads(p.read_text()) for p in paths if p.name != DEVICES}
        self.starts: list[dict] = []           # the start vectors: address, top Network, the tape's own
        self.bound: dict[str, Bound] = Section("the routine")
        self.placed: dict[str, Path] = {}       # field -> the unit that lays out its data word
        self.cell_of: dict[str, str] = {}       # field -> the JDA routine whose entry word holds it
        self.io_fields: set[str] = set()
        self.registers: set[str] = set()        # Records whose fields live in AC or IO
        self.cursors: dict[str, str] = {}       # field -> the cursor on the current object's slot
        self.pool: set[str] = set()             # fields that live in a pool word
        self.homes: dict[str, str] = {}         # field -> "table" (a pointer into its shifts) or "pointer"
        self.held: set[str] = set()             # fields held as the code of their use (held-as-code.md)
        self.code_words: dict[str, int] = {}    # a collection held as a run of code -> the words it takes
        self.walks: dict[str, Walk] = {}        # a collection held as a run of code -> the walk that runs it
        self.stores: dict[str, dict] = {}       # such a collection -> its store routine's place
        self.spelled: dict[str, dict] = {}      # enum -> member -> how its word is spelled
        self.streams: dict[str, str] = {}       # stream -> the instruction that takes it (dpy, hlt)
        self.devices: dict[str, dict] = {}      # field -> the device instruction that reads it
        self.flags: dict[str, int] = {}         # field -> the program flag that holds it
        self.pointers: set[str] = set()         # fields that hold addresses
        self.addresses: dict[str, str] = {}     # field -> the address it always holds
        self.table: dict = Section("[table]")   # the Records laid out field after field in one array
        self.jsp_slots: dict[str, dict] = {}    # a JSP slot's name -> what it jumps to
        self.slot_cursors: dict[str, dict] = {} # a field holding a slot -> field -> the cursor on it
        self.carried: set[str] = set()          # code routines whose jump's word a walk carries
        self.into: dict[str, str] = {}          # field -> the collection's field it holds a place in
        self.pieces: dict[str, list] = {}       # collection field -> (first slot, last slot, C name) laid out
        self.bases: dict[str, Path] = {}        # collection field -> the unit laying out a word of its address
        self.shared: dict[str, str] = {}        # field -> the field whose word it lives in
        self.compiled: list[tuple] = []         # (Function, its statements as run) of every routine compiled
        self.device_file(next((p for p in paths if p.name == DEVICES), None))
        for word in ("constants", "variables"):
            # a program with no literal constant, or no pool word, has none
            if sum(p.get("machine") == word for s in self.specs.values() for p in s.get("place", [])) > 1:
                raise BindError(f"the assembler's {word} are laid out once, by a place machine = {word!r}")
        for path, spec in self.specs.items():
            check_schema(path, spec)
            for f, target in spec.get("into", {}).items():
                self.check_field(path, f)
                self.check_field(path, target)
                self.into[f] = target
                self.pointers.add(f)
            for f, other in spec.get("share", {}).items():
                self.check_field(path, f)
                self.check_field(path, other)
                self.shared[f] = other
            self.registers |= set(spec.get("registers", []))
            for f, cursor in spec.get("cursors", {}).items():
                self.check_field(path, f)
                if isinstance(cursor, dict):
                    for g in cursor:
                        self.check_field(path, g)
                    self.slot_cursors[f] = cursor
                else:
                    self.cursors[f] = cursor
            self.carried |= set(spec.get("walk", {}).get("carry", []))
            for f in spec.get("pool", []):
                self.check_field(path, f)
                self.pool.add(f)
            for f, how in spec.get("homes", {}).items():
                self.check_field(path, f)
                self.homes[f] = how
            for f in spec.get("held_as_code", []):
                self.check_field(path, f)
                self.held.add(f)
            for f, n in spec.get("code_words", {}).items():
                self.check_field(path, f)
                self.code_words[f] = n
            for p in spec.get("place", []):
                if "store" in p:
                    self.check_field(path, p["store"])
                    self.stores[p["store"]] = {**p, "unit": path}
            self.spelled |= spec.get("spell", {})
            self.streams |= spec.get("streams", {})
            for f, n in spec.get("flags", {}).items():
                self.check_field(path, f)
                self.flags[f] = n
            for f, where in spec.get("addresses", {}).items():
                self.check_field(path, f)
                self.addresses[f] = where
            self.table |= spec.get("table", {})
            for p in spec.get("place", []):
                if "jsp_slot" in p:
                    self.jsp_slots[p["jsp_slot"]] = p
            for p in spec.get("place", []) + [{**i, "convention": "INLINE"} for i in spec.get("inline", [])] \
                    + [{**c, "convention": "BLOCK", "code": True} for c in spec.get("code", [])]:
                if "routine" in p:
                    self.bind(path, p)
                for f in p.get("fields", []) + [d for d in p.get("data", []) if "." in d]:
                    self.check_field(path, f)
                    self.placed[f] = path
                if "slots" in p:
                    self.check_field(path, p["slots"])
                    lo, hi = p["range"]
                    count = self.prog.records[p["slots"].split(".")[0]].count
                    if count is None or not 0 <= lo <= hi < count:
                        raise BindError(f"{path.name}: slots {p['slots']} {p['range']}: slots of a collection")
                    self.pieces.setdefault(p["slots"], []).append((lo, hi, f"{self.c_name(p['slots'])}_{octal(lo)}"))
                    self.placed[p["slots"]] = path
                if "base" in p:
                    self.check_field(path, p["base"])
                    self.bases[p["base"]] = path
        self.check_names()

    def device_file(self, path: Path | None):
        """pdp1/devices.toml: which console instruction or sense switch holds
        each input field, which program flag lights each output, and where
        the operator starts each top Network. Presentation: play sees the
        values, never the devices."""
        if path is None:
            raise BindError(f"no {DEVICES}: the devices are bound in one place")
        spec = tomllib.loads(path.read_text())
        check_keys(path, spec, "devices", "the devices")
        for v in spec.get("start", []):
            check_keys(path, v, "start", "[[start]]")
        for f, how in spec.get("console", {}).items():
            self.check_field(path, f)
            self.devices[f] = how if isinstance(how, dict) else {"read": how}
        for f, n in spec.get("lights", {}).items():
            self.check_field(path, f)
            self.flags[f] = n
        fired = set().union(set(), *(runs.runs_of(r.body) for r in self.prog.routines.values()))
        for v in spec.get("start", []):
            if v["network"] not in self.prog.routines or v["network"] in fired:
                raise BindError(f"{path.name}: a start is an address and a top Network: {v}")
            self.starts.append(v)
        if self.starts and sum(bool(v.get("tape")) for v in self.starts) != 1:
            raise BindError(f"{path.name}: one start is the tape's own")
        self.starts.sort(key=lambda v: v["at"])

    def check_names(self):
        """Every value of a binding that names a field, a routine, a member
        or a local names one the RUNS text has, and each name a binding gives
        a C word of its own names nothing else."""
        bound = set(self.bound)
        for f, other in self.shared.items():
            if other in self.shared or other == f:
                raise BindError(f"[share] {f} lives in {other}'s word, which is a word of its own: "
                                f"not {f} itself, and not shared with a third")
        made = self.made_names()
        taken = set(self.prog.routines) | set(self.prog.records) | {self.c_name(f) for f in self.field_names()} \
            | set(self.prog.enums) | {m for ms in self.prog.enums.values() for m in ms} \
            | set().union(*(routine_locals(r) for r in self.prog.routines.values())) | C_WORDS
        if clash := sorted({n for n in made if made.count(n) > 1 or n in taken}):
            raise BindError(f"{clash}: a name a binding gives a cursor, the table, a block, an exit or a slot "
                            f"names nothing else, in the RUNS or in C")
        for r in self.table.get("records", []):
            if self.prog.records.get(r) is None or self.prog.records[r].count is None or self.prog.records[r].stream:
                raise BindError(f"[table] records: {r!r} is no collection of the RUNS")
        self.check_stages()
        homed: dict[str, list[str]] = {}
        for path, spec in self.specs.items():
            for f in spec.get("walk", {}).get("homes", []) + list(spec.get("walk", {}).get("home_in", {})):
                homed.setdefault(f, []).append(path.name)
        if twice := sorted(f for f, units in homed.items() if len(units) > 1):
            raise BindError(f"{twice}: a cursor is homed in one instruction, of one unit ({homed[twice[0]]})")
        for f, how in self.devices.items():
            if len({"read", "sense"} & set(how)) != 1 or "or_into_io" in how and "read" not in how:
                raise BindError(f"{DEVICES}: {f} is read by an instruction (read) or held in a sense switch "
                                f"(sense): {how}")
        for path, spec in self.specs.items():
            def routine(name: str, what: str):
                if name not in self.prog.routines:
                    raise BindError(f"{path.name}: {what} {name!r} is no routine")
            for r in spec.get("registers", []):
                if r not in self.prog.records:
                    raise BindError(f"{path.name}: registers {r!r} is no Record")
            if "repeat" in spec:
                routine(spec["repeat"], "repeat")
            for enum, members in spec.get("spell", {}).items():
                if enum not in self.prog.enums:
                    raise BindError(f"{path.name}: spell.{enum}: no enum {enum}")
                for m, how in members.items():
                    if m not in self.prog.enums[enum]:
                        raise BindError(f"{path.name}: spell.{enum}: {m!r} is no member of {enum}")
                    if isinstance(how, dict):
                        if set(how) - {"routine", "sign", "literal"} or "routine" not in how:
                            raise BindError(f"{path.name}: spell.{enum}.{m}: a routine, sign, literal")
                        if how["routine"] not in self.prog.routines and how["routine"] not in self.jsp_slots:
                            raise BindError(f"{path.name}: spell.{enum}.{m}: {how['routine']!r} is no routine")
                    elif not isinstance(how, int):
                        raise BindError(f"{path.name}: spell.{enum}.{m}: a number or a routine")
            for stream in spec.get("streams", {}):
                if stream not in self.prog.records or not self.prog.records[stream].stream:
                    raise BindError(f"{path.name}: streams: {stream!r} is no stream")
            walk = spec.get("walk", {})
            if "set_after" in walk:
                routine(walk["set_after"], "walk.set_after")
            for proc in walk.get("home_in", {}).values():
                routine(proc, "walk.home_in")
            for f in walk.get("homes", []) + list(walk.get("home_in", {})):
                if f not in self.cursors:
                    raise BindError(f"{path.name}: [walk] homes {f}, which has no cursor ([cursors])")
            if "set_after" in walk and "index" not in walk:
                raise BindError(f"{path.name}: [walk] names the field whose cursor ends the walk (index)")
            if "index" in walk and (walk["index"] not in self.cursors
                                    or "other" in walk and walk["index"] not in walk["other"]):
                raise BindError(f"{path.name}: [walk] index {walk['index']}, which has no cursor in each walk "
                                f"([cursors], [walk.other])")
            for f in [walk.get("index")] + walk.get("homes", []) + list(walk.get("home_in", {})) \
                    + list(walk.get("other", {})) + ([walk["stray"]["after"]] if "stray" in walk else []):
                if f:
                    self.check_field(path, f)
            for r in spec.get("table", {}).get("records", []):
                if r not in self.prog.records:
                    raise BindError(f"{path.name}: table.records {r!r} is no Record")
            for p in spec.get("place", []) + spec.get("inline", []) + spec.get("code", []):
                if "jsp_slot" in p:
                    routine(p["jump"], "jsp_slot jump")
                if "shifts" in p and "routine" not in p and self.homes.get(p["shifts"]) != "table":
                    raise BindError(f"{path.name}: shifts {p['shifts']!r} is no field held in a table of shifts")
                if "routine" not in p:
                    continue
                b = self.bound[p["routine"]]
                own = self.locals_of(b.name, bound)
                for key in ("io", "pool", "spill", "data"):
                    for name in p.get(key, []):
                        if "." in name:
                            self.check_field(path, name)
                        elif name not in own:
                            raise BindError(f"{path.name}: {b.name} {key}: {name!r} is no local of its RUNS")
                for key in ("flags", "homes", "into"):
                    for name in p.get(key, {}):
                        if name not in own:
                            raise BindError(f"{path.name}: {b.name} {key}: {name!r} is no local of its RUNS")
                for f in b.io_reads:
                    self.check_field(path, f)
                if b.skips:
                    enum = self.prog.records[b.skips[0].split(".")[0]].fields[leaf(b.skips[0])][0]
                    if b.skips[1] not in self.prog.enums.get(enum, []):
                        raise BindError(f"{path.name}: {b.name} skips: {b.skips[1]!r} is no member of {enum}")
                runs_here = set(own_routines(self.prog, b.name, bound))
                for key in ("args_done", "exit_after"):
                    if key in p and p[key] not in runs_here:
                        raise BindError(f"{path.name}: {b.name} {key}: {p[key]!r} is no routine it runs")

    def made_names(self) -> list[str]:
        """The names the bindings give C words of their own: the cursors, the
        table, the blocks, the exits and the slots. They never reach the image."""
        return list(self.cursors.values()) + [c for m in self.slot_cursors.values() for c in m.values()] \
            + [c for s in self.specs.values() for c in s.get("walk", {}).get("other", {}).values()] \
            + [self.table[k] for k in ("at", "clear") if k in self.table] \
            + [s["walk"]["stray"]["cursor"] for s in self.specs.values() if "stray" in s.get("walk", {})] \
            + [p[k] for s in self.specs.values() for p in s.get("place", []) for k in ("block", "exit", "jsp_slot")
               if k in p]

    def field_names(self):
        return (f"{r}.{f}" for r, rec in self.prog.records.items() for f in rec.fields)

    def locals_of(self, name: str, bound: set[str]) -> set[str]:
        """The locals of a bound routine's RUNS: its parameters, and every
        name a let or a counted loop of the routines it compiles binds."""
        return set().union(*(routine_locals(self.prog.routines[r]) for r in own_routines(self.prog, name, bound)))

    def check_field(self, path: Path, dotted: str):
        if not _field(dotted):
            raise BindError(f"{path.name}: {dotted!r} is no record.field")
        rec, fld = dotted.split(".")
        if rec not in self.prog.records or fld not in self.prog.records[rec].fields:
            raise BindError(f"{path.name}: no field {dotted}")

    def bind(self, path: Path, p: dict):
        """A routine compiled from RUNS."""
        name = p["routine"]
        if name not in self.prog.routines:
            raise BindError(f"{path.name}: {name} is no routine")
        if p.get("convention") == "JDA" and "entry" not in p:
            raise BindError(f"{path.name}: {name} is JDA: name its entry word (entry)")
        if p.get("code"):
            w = Walk.of(self.prog, self.prog.routines[name], self.held)
            self.walks[w.field] = w
        b = Bound(name, path, p["convention"], p.get("entry"), p.get("ac_param"), p.get("io_param"),
                  p.get("byname"), p.get("result", []), p.get("block"), p.get("block_takes_entry", False),
                  tuple(p["skips"]) if "skips" in p else None, set(p.get("io", [])), p.get("cells", []),
                  p.get("loops"), p.get("shifts"), set(p.get("pool", [])), set(p.get("spill", [])),
                  p.get("inline"), self.pointers, set(p.get("io_reads", [])),
                  None, p.get("pulse", False), p.get("code", False),
                  p.get("args_done"), p.get("data", []), dict(p.get("flags", {})), dict(p.get("homes", {})),
                  dict(p.get("into", {})), p.get("arms"), p.get("exit_after"), tails=p.get("tails"))
        for f in b.into.values():
            self.check_field(path, f)
        for f in [b.entry, b.ac_param, b.io_param, b.byname, b.inline, *b.result, *b.cells] + \
                ([b.skips[0]] if b.skips else []):
            if f:
                self.check_field(path, f)
        for f in [b.entry, *b.cells]:
            if f:
                self.cell_of[f] = name
        self.io_fields |= {f for f in b.io if "." in f}
        if b.io_param:
            self.io_fields.add(b.io_param)
        self.bound[name] = b

    def all_cursors(self) -> set[str]:
        """Every cursor of the main loop's walks and of the slot a field holds."""
        out = set(self.cursors.values())
        for spec in self.specs.values():
            walk = spec.get("walk", {})
            out |= set(walk.get("other", {}).values())
            if "stray" in walk:
                out.add(walk["stray"]["cursor"])
        for cursors in self.slot_cursors.values():
            out |= set(cursors.values())
        if "clear" in self.table:
            out.add(self.table["clear"])
        return out

    def homed_cursors(self) -> set[str]:
        """The cursors some unit holds in an instruction's address field."""
        out = {self.table["clear"]} if "clear" in self.table else set()
        for spec in self.specs.values():
            walk = spec.get("walk", {})
            out |= {self.cursors[f] for f in walk.get("homes", []) + list(walk.get("home_in", {}))}
            out |= set(walk.get("other", {}).values())
        for cursors in self.slot_cursors.values():
            out |= set(cursors.values())
        return out

    def c_name(self, dotted: str) -> str:
        if dotted in self.shared:
            return self.c_name(self.shared[dotted])
        return dotted.replace(".", "_")

    def address(self, dotted: str, slot: int) -> tuple[str, str | None]:
        """The address of a slot of a collection's field, as the C names it,
        and the array of it a binding lays out (None: after the table)."""
        pieces = self.pieces.get(dotted, [])
        for lo, hi, name in pieces + [(lo, hi + 1, name) for lo, hi, name in pieces]:
            if lo <= slot <= hi:        # a slot, else the place just past a piece's last
                return (name if slot == lo else f"{name} + {octal(slot - lo)}"), name
        if self.addresses.get(dotted) == "after table":
            return f"{self.c_name(dotted)} + {octal(slot)}", None
        raise BindError(f"{dotted}[{slot:o}] has no address in the binding")

    def after_table(self) -> list[str]:
        """The collections laid out from the word after the table, each its
        RUNS count of words."""
        return [d for d, where in self.addresses.items() if where == "after table"]

    def table_fields(self) -> list[str]:
        """The fields laid out in the table, in its order."""
        return [f"{r}.{f}" for r in self.table.get("records", []) for f in self.prog.records[r].fields]

    def table_offset(self, dotted: str) -> int:
        off = 0
        for f in self.table_fields():
            if f == dotted:
                return off
            off += self.prog.records[f.split(".")[0]].count
        raise BindError(f"{dotted} is not in the table")

    def table_size(self) -> int:
        return sum(self.prog.records[f.split(".")[0]].count for f in self.table_fields())

    def check_stages(self):
        """A field held as the code of its use is written at one stage and
        read at a later one: no Processor both writes it and reads it."""
        for name, r in self.prog.routines.items():
            if r.kind != "processor":
                continue
            named = [dotted_of(e) for e in walk_expr(r.body) if e[0] == "field"]
            targets = [held_field(t) for x in walk(r.body) if x[0] in ("let", "set")
                       for t in (x[1][1] if x[1][0] == "tuple" else [x[1]])]
            for f in sorted(self.held & set(targets)):
                if named.count(f) > targets.count(f):
                    raise BindError(f"{name}: {f} is held as the code of its use, so it is written at one "
                                    f"stage and read at a later one; {name} writes it and reads it")

    def held_place(self, dotted: str) -> bool:
        """A place held as code: the jump to it. The walk goes on from it
        (`set at = L.f[at]; continue`), or it is copied to a field that does."""
        jumps = {g for w in self.walks.values() for g in w.jumps}
        return dotted in self.held and (dotted in jumps or any(
            dotted_of(s[2]) == dotted and held_field(s[1]) in jumps
            for r in self.prog.routines.values() for s in walk(r.body) if s[0] == "set"))

    def after_walk(self, name: str) -> str:
        """The routine a Network runs right after a walk: where leaving it goes."""
        for r in self.prog.routines.values():
            items = [s for s in r.body if s[0] == "run"]
            for a, b in zip(items, items[1:]):
                if a[1] == name:
                    return b[1]
        raise BindError(f"{name}: no Network runs a routine after it, where leaving the walk goes")

    def coded(self, dotted: str) -> bool:
        """A count held as code: its own shift (held), or a pointer into a
        table of its shifts ([homes] "table")."""
        return dotted in self.held or self.homes.get(dotted) == "table"

    def stored(self, dotted: str) -> bool:
        """The field has a word of its own: data, a pool word, or an entry word."""
        return dotted in self.placed or dotted in self.cell_of or dotted in self.pool

    def in_register(self, dotted: str, unit: Path | None = None) -> bool:
        """The field lives in AC or IO, not in a word of its own. The entry
        word of a routine of another unit is, to this unit, what AC carries
        into the call and out of it."""
        if dotted in self.cell_of and unit is not None and self.bound[self.cell_of[dotted]].unit != unit:
            return dotted.split(".")[0] in self.registers and dotted not in self.placed and dotted not in self.pool
        return dotted.split(".")[0] in self.registers and not self.stored(dotted)


class Unit:
    """One binding: the RUNS routines and fields it places, in tape order."""

    def __init__(self, binds: Bindings, path: Path, code: dict[str, RunCode] | None = None):
        self.binds = binds
        self.prog = binds.prog
        self.path = path
        self.code = code or {}                  # collection held as a run of code laid out here -> its RunCode
        self.spec = binds.specs[path]
        self.externs: set[str] = set()
        self.cells_used: set[str] = set()
        self.callees: set[str] = set()
        self.pool_locals: set[str] = set()
        self.tables: dict[str, list[int]] = {}  # table-held field -> the shift counts it takes, in text order
        self.kinds: dict[str, str] = {}         # count held as code -> the operator of its use
        self.templates: dict[str, str] = {}     # TEMPLATE name -> its C text (template)
        self.copies_of: dict[str, str] = {}     # field -> a field it is copied from or to (union-find)
        self.walk = Section(f"{path.name} [walk]", self.spec.get("walk", {}))  # the cursors' walk over the slots
        self.homed: dict[str, str | None] = {}  # cursor -> the Processor its home is in (None: first access)
        for f in self.walk.get("homes", []):
            self.homed[binds.cursors[f]] = None
        for f, proc in self.walk.get("home_in", {}).items():
            self.homed[binds.cursors[f]] = proc
        for c in self.walk.get("other", {}).values():
            self.homed[c] = None
        for f, cursors in self.spec.get("cursors", {}).items():
            if isinstance(cursors, dict):       # the cursors on a slot a field holds: homed here
                for c in cursors.values():
                    self.homed[c] = None
        self.home_kind: dict[str, str] = {}     # cursor -> its home's instruction ("LAC" in a guard), once laid out
        self.named: set[str] = set()            # routines a member's word names
        self.named_data: set[str] = set()       # arrays another unit lays out that the code names
        self.typedefs: set[str] = set()
        self.carried: dict[str, str] = {}      # a jump's home -> the field whose word it carries
        self.cleared: str | None = None        # the cursor the table's clearing loop is homed in
        self.exit = next((p["exit"] for p in self.spec.get("place", []) if "exit" in p), None)
        self.labels = 0
        self.pools_used: set[str] = set()      # pool fields the unit's code names
        self.shared_keys: dict[tuple, str] = {} # (Network, its arguments) run last by branches -> label
        self.args_done_after: str | None = None
        self.run_fields: set[str] = set()      # collections held as a run of code that this unit lays out
        self.homed_pointers: set[str] = set()  # fields held in the address of an instruction
        self.homed_locals: dict[str, str] = {}  # a homed local of a routine laid out once -> the field it points into
        self.duff_homes: set[str] = set()      # jumps into a run of a counted loop's bodies
        self.current: Bound | None = None       # the bound routine being flattened (flat_routine)
        self.copies = 0
        self.local_base: dict[str, str] = {}   # a copy's own local -> the Processor's local
        self.slot_data: dict[str, dict[int, str]] = {}   # field -> slot -> its data word, laid out in code
        self.home_kinds: dict[str, str] = {}   # a homed local -> the instruction its home is ("LIO")
        self.spellings: dict[str, str] = {}    # a data local -> the instruction it is spelled as
        self.home_laid_out: set[str] = set()   # those whose home is laid out already

    def pool_word(self, f: str) -> str:
        """A pool word's declaration. One that holds a member of an enum
        whose members are spelled as routines holds a routine's address: a
        pointer to the routines' type, which the enum names."""
        rec, fld = f.split(".")
        enum = self.prog.records[rec].fields[fld][0]
        spelled = self.binds.spelled.get(enum, {})
        routines = [how["routine"] for how in spelled.values() if isinstance(how, dict) and "routine" in how]
        if enum not in self.prog.enums or not routines or len(routines) != len(spelled):
            return f"POOL word {self.binds.c_name(f)};"
        kinds = set()
        for r in routines:
            if r in self.binds.jsp_slots:
                kinds.add(("JSP", {"io": "io_word", "ac": "word"}[self.binds.jsp_slots[r]["returns"]]))
            elif self.binds.bound[r].params():
                raise BindError(f"{self.path.name}: {r}, which {f} may name, takes arguments")
            else:
                kinds.add((self.binds.bound[r].convention, self.binds.bound[r].returns()))
        if len(kinds) != 1:
            raise BindError(f"{self.path.name}: the routines {f} may name differ in type")
        (conv, ret), = kinds
        self.typedefs.add(f"typedef {ret} {enum}(void) {conv};")
        return f"POOL {enum} *{self.binds.c_name(f)};"

    def held_elsewhere(self, text: str) -> list[str]:
        """The words the unit's code names that the main loop's walk holds:
        a cursor homed in another unit's instruction, else a pool word, and
        the object table, which another unit lays out."""
        out = []
        own = set(self.homed) | {self.cleared} | ({self.walk["stray"]["cursor"]} if "stray" in self.walk else set())
        for c in sorted(self.binds.all_cursors() - own):
            if re.search(rf"\b{c}\b", text):
                out.append(f"extern HOMED word *{c};" if c in self.binds.homed_cursors() else f"POOL word *{c};")
        if any(p.get("table") for p in self.spec["place"]):
            return out
        for name in [self.binds.table.get("at")] + [self.binds.c_name(d) for d in self.binds.after_table()]:
            if name and re.search(rf"\b{name}\b", text):
                out.append(f"extern word {name}[];")
        return out

    def copy_words(self) -> list[str]:
        """The words the copies of a Processor keep their own: homed locals
        start at address 0, as the source writes them with no operand; a
        data local is the instruction it is compared as, at address 0; a
        slot of a field laid out in code holds its RUNS initial value."""
        out = []
        for name, base in sorted(self.local_base.items()):
            if base in self.current_homes():
                out.append(f"HOMED word *{name} = 0;")
            elif name in self.spellings:
                out.append(f"insn {name} = {self.spellings[name]}(0);")
            else:
                raise BindError(f"{self.path.name}: {name} is a data word compared with no home")
        for d, slots in sorted(self.slot_data.items()):
            rec, fld = d.split(".")
            init = self.prog.records[rec].fields[fld][1]
            for k, name in sorted(slots.items()):
                if k >= self.prog.records[rec].count:
                    raise BindError(f"{self.path.name}: {d} has no slot {octal(k)}")
                e = init[1][k] if init is not None and init[0] == "slots" else init
                if d in self.binds.into and e is not None and e[0] == "num":
                    out.append(f"word *{name} = {self.address(self.binds.into[d], e[1])};")
                else:
                    out.append(f"word {name} = {Function.constant(e) if e is not None else '0'};")
        return out

    def address(self, dotted: str, slot: int) -> str:
        """The address of a slot of a collection's field, the array it lies
        in declared when another unit lays it out."""
        text, array = self.binds.address(dotted, slot)
        if array:
            self.named_data.add(array)
        return text

    def current_homes(self) -> set[str]:
        return {h for p in self.spec.get("place", []) if "routine" in p for h in p.get("homes", {})}

    def initial(self, dotted: str) -> str:
        rec, fld = dotted.split(".")
        e = self.prog.records[rec].fields[fld][1]
        return Function.constant(e) if e is not None else "0"

    def store_of(self, f: str) -> tuple[str, str] | None:
        """The store routine of a collection held as a run of code, and the
        register local that holds the word it stores, when the binding lays one out here."""
        st = self.binds.stores.get(f)
        if st is None or st["unit"] != self.path or f not in self.code or not self.code[f].stored:
            return None
        name = self.binds.c_name(f)
        return f"{name}_lay_io", f"{name}_io"

    def jump_words(self, f: str | None = None) -> list[str]:
        """The data word a jump within a member's code is built in, for each
        collection laid out here whose members' code, as pdp1cc compiles
        it, jumps within itself."""
        fields = [f] if f else sorted(self.code)
        return [f"{self.binds.c_name(g)}_jump" for g in fields if g in self.code and self.code[g].jumps]

    def run_code(self, c: Path) -> dict[str, RunCode]:
        """pdp1cc's words for the members of each collection this unit lays
        out as a run of code, read from the unit's C (c): whether a member
        jumps within itself, and for the store routine the binding chooses,
        how many times in a row the members hold the word it stores."""
        try:
            words = dialect.template_words(front.parse(c))
        except (dialect.DialectError, select.SelectError) as e:
            raise BindError(f"{self.path.name}: the members' code: {e}") from e
        out = {}
        for f in sorted(self.run_fields):
            members = [words[self.template_name(f, m)] for m in self.binds.walks[f].arms]
            stored = 0
            if self.binds.stores.get(f, {}).get("unit") == self.path:
                try:
                    stored = dialect.repeated_run(members)[1]
                except dialect.DialectError as e:
                    raise BindError(f"{self.path.name}: store {f}: {e}") from e
            out[f] = RunCode(any(select.jumps_within(t) for t in members), stored)
        return out

    def template_name(self, f: str, member: str) -> str:
        return f"{self.binds.c_name(f)}_{member}"

    def store_routine(self, p: dict) -> list[str]:
        """A JSP routine that stores IO through the cursor into a collection
        held as code, as many times as its members hold that word in a row,
        stepping it each time."""
        f = p["store"]
        cursors = [g for g, into in self.binds.into.items() if into == f and g in self.binds.cell_of]
        if len(cursors) != 1:
            raise BindError(f"{self.path.name}: store {f}: one entry word steps through it, not {cursors}")
        self.cells_used.add(cursors[0])
        cursor = self.binds.c_name(cursors[0])
        name, _ = self.store_of(f)
        return [f"JSP void {name}(register insn w)", "{",
                *[f"    *{cursor}++ = w;" for _ in range(self.code[f].stored)], "    return;", "}"]

    def run_templates(self, f: str) -> list[str]:
        """Each member's code: its arm of the walk, compiled by the
        statement compiler as a TEMPLATE whose parameters are what AC and IO
        hold as the walk runs."""
        w = self.binds.walks[f]
        wb = self.binds.bound[w.routine]
        io_set = wb.io | self.binds.io_fields
        regs = w.registers(self.binds)
        ac, io = [g for g in regs if g not in io_set], [g for g in regs if g in io_set]
        if len(ac) > 1 or len(io) > 1:
            raise BindError(f"{w.where}: the walk keeps one value in AC and one in IO, not {ac + io}")
        params = ", ".join([f"word {leaf(g)}" for g in ac] + [f"register word {leaf(g)}" for g in io]) or "void"
        own = {g: leaf(g) for g in ac + io}
        out = []
        for member, stmts in w.arms.items():
            tb = Bound(w.routine, self.path, "TEMPLATE", io=set(wb.io), pulse=wb.pulse)
            fn = Function(self, tb, own, typed(self.prog, stmts, routine_locals(self.prog.routines[w.routine]),
                                               w.routine))
            fn.pulsed = wb.pulse                # a walk that waits for a pulse is entered with one pending
            out += [f"static TEMPLATE void {self.template_name(f, member)}({params})", "{", *fn.compile(), "}"]
        return out

    def shift_initial(self, f: str, e=False) -> str:
        """The word of a count held as the code of its use: that code with
        the count, or the unset shift for a field with no initial value."""
        if e is False:
            e = self.initial_of(f)
        if e is None:
            return "SHIFT_UNSET"
        if e[0] != "num":
            raise BindError(f"{self.path.name}: {f} is held as the code of its use: its initial value is a count")
        return self.code_word(f, octal(e[1]))

    def code_word(self, f: str, count: str) -> str:
        """The one word of f's template with this count (C text)."""
        return f"CODE({self.template(f)}, {count})"

    def template(self, f: str) -> str:
        """The TEMPLATE function of the shift f's count is held as: the use,
        as the statement compiler writes a shift by a constant, with the
        count its VALUE. Fields copied to one another share one."""
        kind = self.shift_kind(f)
        name = f"{self.binds.c_name(self.copy_root(f))}_code"
        if kind in PAIR_OPS:
            text = f"static TEMPLATE void {name}(word hi, register word lo, VALUE word n) {{ {kind}(hi, lo, n); }}"
        elif kind in ("ral", "rar"):
            text = f"static TEMPLATE void {name}(word a, VALUE word n) {{ a = {kind}(a, n); }}"
        else:
            op = {"sar": ">>", "sal": "<<"}[kind]
            text = f"static TEMPLATE void {name}(word a, VALUE word n) {{ a = a {op} n; }}"
        self.templates[name] = text
        return name

    def slots(self, p: dict) -> list[str]:
        """Slots of a collection's field laid out as data words, with their
        RUNS initial values, then `reserve` words no rule reads."""
        rec, fld = p["slots"].split(".")
        lo, hi = p["range"]
        e = self.prog.records[rec].fields[fld][1]
        values = e[1][lo:hi + 1] if e is not None and e[0] == "slots" else [e] * (hi - lo + 1)
        name = f"{self.binds.c_name(p['slots'])}_{octal(lo)}"
        if p["slots"] in self.binds.held:
            words = ", ".join(self.shift_initial(p["slots"], v) for v in values)
            return [f"shift {name}[{octal(hi - lo + 1)}] = {{ {words} }};"]
        out = [f"word {name}[{octal(hi - lo + 1)}] = {{ {', '.join(Function.constant(v) for v in values)} }};"]
        if p.get("reserve"):
            out.append(f"RESERVE word {name}_spare[{octal(p['reserve'])}];")
        return out

    def table_words(self) -> str:
        """The object table's words. The tape does not load them, and a new
        game clears them before anything reads them: each field's RUNS
        initial value is its zero word. Then the room of each collection
        that lies after the table."""
        for f in self.binds.table_fields():
            rec, fld = f.split(".")
            e = self.prog.records[rec].fields[fld][1]
            if not (e == ("num", 0) or e[0] == "name" and self.binds.spelled.get(
                    resolve(self.prog, e[1], self.prog.records[rec].fields[fld][0], f), {}).get(e[1]) == 0):
                raise BindError(f"{self.path.name}: {f} is not on the tape, so it starts at its zero word")
        after = [f"RESERVE word {self.binds.c_name(d)}"
                 f"[{octal(self.binds.code_words.get(d, self.prog.records[d.split('.')[0]].count))}];"
                 for d in self.binds.after_table()]
        return "\n".join([f"RESERVE word {self.binds.table['at']}[{octal(self.binds.table_size())}];"] + after)

    def check_unstored(self):
        """A field with no data word cannot carry an initial value onto the
        tape: an entry word is punched as 0, a register holds what the
        caller left, a pool word, a cursor or an instruction what the
        program first stores there. Its RUNS initial value must be 0."""
        fields = set(self.binds.pool) | set(self.binds.homes) | self.binds.held | set(self.binds.slot_cursors) \
            | {f for f in self.binds.field_names() if self.binds.in_register(f, self.path)}
        for p in self.spec.get("place", []) + self.spec.get("inline", []):
            if "routine" in p:
                b = self.binds.bound[p["routine"]]
                fields |= {b.entry, b.ac_param, b.io_param, b.byname, *b.result, *b.cells} - {None}
        for f in sorted(fields - set(self.binds.placed)):
            rec, fld = f.split(".")
            e = self.prog.records[rec].fields[fld][1]
            if e is not None and e != ("num", 0):
                raise BindError(f"{self.path.name}: {f} has no data word, so its initial value is 0")

    def shift_homes(self, stmts):
        """Each field held in a shift instruction: the shift it is, from the
        operators that take it as their count (a pair shift, `>>`, `<<`, a
        rotate of one word); for one held as a pointer into a table, the
        counts the text sets it to, in order. A copy of one field to
        another joins them: a field held as its instruction whose count
        only reaches a shift through copies (a table the count is picked
        from) is the shift its copies are."""
        def kind(f: str, op: str, where: str):
            if self.kinds.setdefault(f, op) != op:
                raise BindError(f"{where}: {f} is one shift instruction, {self.kinds[f]}")

        for s in walk(stmts):
            if s[0] in ("let", "set") and s[2][0] == "call" and s[2][1] in PAIR_OPS and len(s[2][2]) == 3 \
                    and self.binds.coded(f := dotted_of(s[2][2][2])):
                kind(f, s[2][1], s[-1])
            for e in walk_expr([x for x in s[1:-1] if isinstance(x, tuple)]):
                if e[0] == "bin" and e[1] in (">>", "<<") and self.binds.coded(f := dotted_of(e[3])):
                    kind(f, {">>": "sar", "<<": "sal"}[e[1]], s[-1])
                elif e[0] == "call" and e[1] in ("ral", "rar") and len(e[2]) == 2 \
                        and self.binds.coded(f := dotted_of(e[2][1])):
                    kind(f, e[1], s[-1])
            if s[0] == "set" and (to := held_field(s[1])) and (src := held_field(s[2])):
                self.copies_of[self.copy_root(to)] = self.copy_root(src)
            if s[0] == "set" and self.binds.homes.get(f := dotted_of(s[1])) == "table":
                if s[2][0] != "num":
                    raise BindError(f"{s[-1]}: {f} is a table entry, so it is set to a number")
                if s[2][1] not in (table := self.tables.setdefault(f, [])):
                    table.append(s[2][1])

    def copy_root(self, f: str) -> str:
        while f in self.copies_of and self.copies_of[f] != f:
            f = self.copies_of[f]
        return f

    def initial_of(self, dotted: str):
        rec, fld = dotted.split(".")
        return self.prog.records[rec].fields[fld][1]

    def holds_shift(self, f: str) -> bool:
        """f holds a shift instruction: it is held as one, or copied to or from one."""
        return f in self.binds.held or any(
            self.copy_root(g) == self.copy_root(f) for g in self.kinds if g in self.binds.held)

    def word_type(self, f: str) -> str:
        return "shift" if self.holds_shift(f) else "word"

    def copied_kinds(self) -> None:
        """A field held as its shift instruction takes the kind of the
        shifts it is copied from or to. A routine of the unit whose AC
        result holds such a shift returns it as one."""
        for f in sorted(self.binds.held):
            if f not in self.kinds:
                kin = {self.kinds[g] for g in self.kinds if self.copy_root(g) == self.copy_root(f)}
                if len(kin) > 1:
                    raise BindError(f"{self.path.name}: {f} is copied to and from shifts of kinds {sorted(kin)}")
                if kin:
                    self.kinds[f] = kin.pop()
        for p in self.spec["place"]:
            b = self.binds.bound.get(p.get("routine", ""))
            if b and b.result and self.holds_shift(b.result[0]):
                b.returns_shift = True

    def shift_kind(self, f: str) -> str:
        if f not in self.kinds:
            raise BindError(f"{self.path.name}: {f} is held in a shift instruction, but no shift of this "
                            f"unit takes it as its count")
        return self.kinds[f]

    def shift_table(self, f: str) -> list[int]:
        if f not in self.tables:
            raise BindError(f"{self.path.name}: {f} is a table of shifts, but no routine of this unit sets it "
                            f"to a count")
        return self.tables[f]

    def start_at(self, b: Bound) -> str:
        """A top Network the operator starts is laid out at its start
        address, its first word where the start goes (`start 500`), unless
        the binding lays out start vectors that jump to it."""
        vectors = any(p.get("machine") == "start vectors" for s in self.binds.specs.values()
                      for p in s.get("place", []))
        v = next((v for v in self.binds.starts if v["network"] == b.name), None)
        if vectors or v is None:
            return ""
        if b.convention != "BLOCK":
            raise BindError(f"{self.path.name}: {b.name} is started at {octal(v['at'])}: it is a BLOCK")
        return f"AT({octal(v['at'])}) {'START ' if v.get('tape') else ''}"

    def routine(self, b: Bound) -> list[str]:
        out = []
        r = self.prog.routines[b.name]
        self.pool_locals |= b.pool
        if b.block:
            own = {f: leaf(f) for f, _ in b.params()}
            wrapper = Function(self, b, own, [])
            if not b.block_takes_entry:
                wrapper.emit(1, f"{wrapper.cell(b.entry)} = {leaf(b.entry)};")
            args = ", ".join(leaf(f) for f, _ in b.params(block=True))
            wrapper.emit(1, f"return {b.block}({args});")
            out += [b.declaration(), "{", *wrapper.out, "}"]
            fn = Function(self, b, {f: leaf(f) for f, _ in b.params(block=True)}, self.arguments(self.flat_routine(r)))
            out += [b.declaration(block=True), "{", *fn.compile(), "}"]
        else:
            fn = Function(self, b, {f: leaf(f) for f, _ in b.params()}, self.arguments(self.flat_routine(r)))
            out += [self.start_at(b) + b.declaration(definition=True), "{", *fn.compile(), "}"]
        self.binds.compiled.append((fn, self.arguments(self.as_run)))
        if b.skips:
            self.check_skips(b, self.as_run)
        return out

    def check_skips(self, b: Bound, stmts: list):
        """A skip return is a count the routine's sets of the field add to
        (skip_return): the RUNS field's last value is the outcome only when
        every path sets the field, and sets the skip member at most once,
        last. A jump into another routine with the same skip return leaves
        the rest to it."""
        field, skip = b.skips
        loops: list[list] = []

        def go(stmts: list, states: frozenset | None) -> frozenset | None:
            for s in stmts:
                if states is None:
                    return None
                op, where = s[0], s[-1] if isinstance(s[-1], str) else ""
                if op in ("let", "set") and s[1][0] != "tuple" and dotted_of(s[1]) == field:
                    if "skip" in states:
                        raise BindError(f"{where}: {field} is {b.name}'s skip return, set after it took {skip}")
                    states = frozenset({"skip" if s[2][0] == "member" and s[2][2] == skip else "other"})
                elif op == "if":
                    outs = [go(body, states) for _, body in s[1]] + [go(s[2], states)]
                    live = [x for x in outs if x is not None]
                    states = frozenset().union(*live) if live else None
                elif op in ("loop", "for", "slots"):
                    top = states
                    for _ in range(8):
                        loops.append([])
                        end = go(s[-2], top)
                        exits = loops.pop()
                        new = top | (end or frozenset()) | frozenset().union(frozenset(), *exits)
                        if new == top:
                            break
                        top = new
                    states = top
                elif op in ("break", "continue"):
                    if loops:
                        loops[-1].append(states)
                    return None
                elif op == "shared":
                    states = go(s[2], states)
                elif op == "call" and self.binds.bound[s[1]].skips == b.skips:
                    if "skip" in states:
                        raise BindError(f"{where}: {field} took {skip}, then {s[1]} sets it again")
                    return None
                elif op == "return":
                    exit_(states, where)
                    return None
            return states

        def exit_(states: frozenset, where: str):
            if "unset" in states:
                raise BindError(f"{where}: {field} is {b.name}'s skip return: set it on every path")
        end = go(stmts, frozenset({"unset"}))
        if end is not None:
            exit_(end, b.name)

    def flat(self, r: runs.Routine, names: dict | None = None, tail: bool = True) -> list:
        """A routine's statements in the order the PDP-1 runs them: a
        Processor's body; a Network's Processors in the order it fires
        them, under its guards and loops, with a call where it runs another
        bound routine. A run's arguments stand for the routine's parameters:
        the slot the cursors point at, or a slot by number."""
        names = names or {}
        local_names = routine_locals(r)
        body = typed(self.prog, substitute(list(r.body), names), local_names, r.name)
        if r.kind == "processor":
            if (cleared := self.clears_table(body)) is not None:
                return [cleared]
            return body
        return self.flat_body(body, r, tail=tail)

    def label(self, what: str) -> str:
        self.labels += 1
        return f"{what}{self.labels}"

    def flat_routine(self, r: runs.Routine) -> list:
        """A bound routine's statements. A Network it runs as the last thing
        of several branches is laid out once, where the last of them runs
        it, and the others jump there."""
        self.args_done_after = self.binds.bound[r.name].args_done if r.name in self.binds.bound else None
        self.current = self.binds.bound[r.name]
        self.copies = 0
        stmts = self.flat(r)
        runs_at: list[str] = []

        def collect(items):
            for s in items:
                if s[0] == "shared":
                    runs_at.append(s[1])
                    collect(s[2])
                elif s[0] == "if":
                    for _, b in s[1]:
                        collect(b)
                    collect(s[2])
                elif s[0] in ("loop", "slots"):
                    collect(s[-2])
        collect(stmts)
        self.as_run = stmts                     # each branch with its own copy of a shared tail
        seen: dict[str, int] = {}

        def rebuild(items):
            out = []
            for s in items:
                if s[0] == "shared":
                    seen[s[1]] = seen.get(s[1], 0) + 1
                    if runs_at.count(s[1]) == 1:
                        out += rebuild(s[2])
                    elif seen[s[1]] == runs_at.count(s[1]):
                        out += [("label", s[1], s[-1])] + rebuild(s[2])
                    else:
                        out.append(("goto", s[1], s[-1]))
                elif s[0] == "if":
                    out.append(("if", [(c, rebuild(b)) for c, b in s[1]], rebuild(s[2]), s[3]))
                elif s[0] in ("loop", "slots"):
                    out.append((*s[:-2], rebuild(s[-2]), s[-1]))
                else:
                    out.append(s)
            return out
        return rebuild(stmts)

    def flat_body(self, items: list, r: runs.Routine, in_slots: bool = False, tail: bool = False) -> list:
        """tail: the routine ends where items end."""
        out: list = []
        back = None
        for n, s in enumerate(items):
            op = s[0]
            last = tail and n == len(items) - 1
            if back and op == "run" and s[1] == back:
                back = None                 # the code jumps back into it
                continue
            if op == "if":
                out.append(("if", [(c, self.flat_body(b, r, in_slots, last)) for c, b in s[1]],
                            self.flat_body(s[2], r, in_slots, last), s[3]))
            elif op == "loop":
                out.append(("loop", s[1], self.flat_body(s[2], r, in_slots), s[3]))
            elif op == "for":
                _, var, lo, hi, body, where = s
                out.append(("slots", var, lo, hi, self.flat_body(body, r, True), where))
            elif op == "match":
                out.append(self.dispatch(s))
            elif op in ("break", "wait", "stop"):
                out.append(s)
            elif op == "run":
                name, args = s[1], s[2]
                if name in self.binds.bound and name != r.name:
                    params = self.prog.routines[name].params if name in self.prog.routines else \
                        [a[1] for a in args if a[0] == "name"]
                    if args != [("name", p) for p in params] or not set(params) <= set(r.params):
                        raise BindError(f"{s[-1]}: run {name} passes only the slot the cursors point at")
                    self.callees.add(name)
                    out.append(("call", name, {}, s[-1]))
                    callee = self.binds.bound[name]
                    if callee.convention == "BLOCK" and not callee.code and not last:
                        raise BindError(f"{s[-1]}: {name} is a block, entered by a jump that does not come back: "
                                        f"run it as the last thing {r.name} does")
                    if callee.code:
                        # code a Record holds jumps back to the routine the Network runs next
                        if n + 1 >= len(items) or items[n + 1][0] != "run":
                            raise BindError(f"{s[-1]}: {name} runs code that jumps back: run where next")
                        callee.back = items[n + 1][1]
                    back = callee.back
                    if back and (n + 1 >= len(items) or items[n + 1][:3] != ("run", back, args)):
                        raise BindError(f"{s[-1]}: {name} jumps back to {back}, so run {back}"
                                        f"({', '.join(a[1] for a in args)}) comes next")
                    continue
                inner = self.prog.routines.get(name)
                if inner is None:
                    raise BindError(f"{s[-1]}: {name} is neither ported nor bound")
                body = self.flat(inner, dict(zip(inner.params, args)), last)
                if inner.kind == "processor":
                    body = self.own_copy(body, s[-1])
                if name == self.current.exit_after:
                    out.append(("exit_next", s[-1]))
                if inner.kind == "processor" and has_return(inner.body) and (in_slots or n < len(items) - 1):
                    end = self.label("done")
                    body = returns_to(body, end) + [("label", end, s[-1])]
                homes = {f for f, proc in self.walk.get("home_in", {}).items() if proc == name}
                if inner.kind == "network" and n == len(items) - 1:
                    key = self.shared_keys.setdefault((name, repr(args)), name if not args else
                                                      f"{name}_{len(self.shared_keys)}")
                    out.append(("shared", key, mark_homes(body, homes), s[-1]))
                    continue
                out += mark_homes(body, homes)
                if name == self.walk.get("set_after"):
                    out.append(("cursors", s[-1]))
                if name == self.args_done_after:
                    out.append(("args_done", s[-1]))
                for f, st in self.binds.stores.items():
                    if st["loaded"] == name and st["unit"] == self.path:
                        out.append(("load_io", f, s[-1]))
            else:
                raise BindError(f"{s[-1]}: cannot compile {op} in a Network")
        return out

    def own_copy(self, body: list, where: str) -> list:
        """A Processor laid out at each run keeps its own words for the
        locals the binding gives words of their own (a home, a data word):
        each copy names them apart. Its data words, and the slots of a
        collection's field it names that the binding lays out in its code,
        are laid out at the copy's end (data_here)."""
        b = self.current
        own = set(b.homes) | set(b.into) | {d for d in b.data if "." not in d}
        mine = own & {x[1][1] for x in walk(body) if x[0] == "let" and x[1][0] == "name"}
        fields = [d for d in b.data if "." in d and self.prog.records[d.split(".")[0]].count]
        if not mine and not any(x[0] == "index" and dotted_of(x[1]) in fields for x in walk_expr(body)):
            return body
        self.copies += 1
        names = {n: ("name", f"{n}_{self.copies}") for n in sorted(mine)}
        for n, renamed in names.items():
            self.local_base[renamed[1]] = n
        body = substitute(body, names)
        data = []
        for d in b.data:
            if d in names:
                data.append(names[d][1])
            elif d in fields:
                for k in sorted({x[2][1] for x in walk_expr(body) if x[0] == "index" and dotted_of(x[1]) == d
                                 and x[2][0] == "num"}):
                    name = self.slot_data.setdefault(d, {}).setdefault(k, f"{self.binds.c_name(d)}_{octal(k)}")
                    data.append(name)
        return body + [("data_here", data, where)] if data else body

    def dispatch(self, s) -> tuple:
        """A match over a field whose members are spelled as the routines its
        arms run: a jump through the field's word. The jump passes the
        scrutinee's slot (the cursors point at it), so each arm's run passes
        exactly that."""
        _, e, arms, where = s
        passed = [e[2]] if e[0] == "index" else []
        for member, body in arms.items():
            enum = resolve(self.prog, member, field_type(self.prog, e), where)
            how = self.binds.spelled.get(enum, {}).get(member)
            if body and body[0][0] == "unreachable" and how == 0:
                continue
            named = how.get("routine") if isinstance(how, dict) else None
            if named in self.binds.jsp_slots:       # a slot that jumps on to another routine
                named = self.binds.jsp_slots[named]["jump"] if body and body[0][1] != named else named
            if not (len(body) == 1 and body[0][0] == "run" and named == body[0][1]):
                raise BindError(f"{where}: {member} runs {body}, not the routine its word names")
            if body[0][2] != passed:
                raise BindError(f"{where}: {member} runs {body[0][1]} with {body[0][2]}; "
                                f"the jump through the word passes {passed}")
        return ("dispatch", e, where, [body[0][1] for body in arms.values() if body[0][0] == "run"])

    def clears_table(self, body: list):
        """A Processor that sets every field of the table's Records to its
        zero word in every slot: the clearing loop over the whole table."""
        table = self.binds.table
        if not table or not body or any(x[0] != "for" for x in body):
            return None
        cleared = set()
        for _, var, lo, hi, inner, where in body:
            for x in inner:
                d = dotted_of(x[1][1]) if x[0] == "set" and x[1][0] == "index" else None
                if d is None or x[1][2] != ("name", var) or not self.zero(x[2]):
                    return None
                rec = d.split(".")[0]
                if lo != ("num", 0) or hi != ("num", self.prog.records[rec].count - 1):
                    return None
                cleared.add(d)
        if cleared != set(self.binds.table_fields()):
            return None
        return ("clear", body[0][-1])

    def zero(self, e) -> bool:
        if e == ("num", 0):
            return True
        return e[0] == "member" and self.binds.spelled.get(e[1], {}).get(e[2]) == 0

    def arguments(self, stmts: list) -> list:
        """The sets of a callee's parameter fields just before its call are
        the call's arguments. A field that lives in a register is passed in
        it. A jump into the callee's block stores its entry word itself, as
        jda would have, and passes it in AC."""
        out: list = []
        for s in stmts:
            if s[0] == "if":
                out.append(("if", [(c, self.arguments(b)) for c, b in s[1]], self.arguments(s[2]), s[3]))
                continue
            if s[0] == "loop":
                out.append(("loop", s[1], self.arguments(s[2]), s[3]))
                continue
            if s[0] == "shared":
                out.append(("shared", s[1], self.arguments(s[2]), s[3]))
                continue
            if s[0] != "call":
                out.append(s)
                continue
            callee = self.binds.bound[s[1]]
            jump = self.jumps(callee, s, stmts)
            params = [f for f, _ in callee.params(block=jump)]
            args = {f: as_field(f) for f in params if self.binds.in_register(f, self.path) and f != callee.inline}
            while out and out[-1][0] == "set" and (target := dotted_of(out[-1][1])) in params \
                    and target not in args and not (jump and target == callee.entry):
                args[target] = out.pop()[2]
            if jump and callee.entry in params:
                args[callee.entry] = as_field(callee.entry)
            if missing := [f for f in params if f not in args]:
                raise BindError(f"{s[-1]}: run {callee.name} without setting {missing} just before")
            out.append(("call", s[1], args, s[-1]))
        return out

    def jumps(self, callee: Bound, call, stmts: list) -> bool:
        """A run of a routine of this unit that has a block, as the last
        thing a routine does, is a jump into the block."""
        return bool(callee.block) and callee.unit == self.path and stmts[-1] is call

    def machine(self, p: dict, head: list[str]) -> list[str]:
        """Words the PDP-1 and its operator need, which no game rule reads.
        The sequence break: the machine saves AC, PC and IO in words 0-2
        and runs word 3, a jump to the flush, which resumes the interrupted
        program. A jump: a start address, the tape's own when `start`. A JSP
        slot: a routine the operator may rewrite in place, by default a
        jump to another, with room after it. The assembler's pools: the
        literal constants and the pool words. The patch space: room for the
        operator's patches."""
        if p.get("machine") == "constants":
            return ["CONSTANTS();"]
        if p.get("machine") == "variables":
            return ["VARIABLES();"]
        if p.get("machine") == "patch space" and "reserve" not in p:
            raise BindError(f"{self.path.name}: the patch space is reserve words long")
        if p.get("machine") == "patch space":
            return [f"RESERVE word patch_space[{octal(p['reserve'])}];"]
        if p.get("machine") == "sequence break":
            head += ["typedef void resume_point(word ac, register word io) BLOCK;",
                     "BLOCK void flush_sequence_break(void);"]
            return ["AT(0) RESERVE word break_ac;", "RESERVE resume_point *break_pc;", "RESERVE word break_io;",
                    "BLOCK void sequence_break(void)", "{", "    return flush_sequence_break();", "}"]
        if p.get("machine") == "sequence break flush":
            # PDP-1 back-end runtime, not RUNS: the flush (sbf) clears the
            # typewriter's flag (tyi), restores IO and AC from words 2 and 0,
            # leaves sequence break mode (lsm) and resumes at word 1. Play
            # cannot reach it: the tape never executes esm (no 720055 in
            # oracle.lst), so a break happens only on a machine another
            # program left in sequence break mode, before the game ran.
            return ["BLOCK void flush_sequence_break(void)", "{", "    tyi();", "    register word io = break_io;",
                    "    word ac = break_ac;", "    lsm();", "    return break_pc(ac, io);", "}"]
        if "jsp_slot" in p:
            ret = {"io": "io_word", "ac": "word"}[p["returns"]]
            head.append(f"JSP {ret} {p['jump']}(void);")
            out = [f"AT({octal(p['at'])}) JSP {ret} {p['jsp_slot']}(void)", "{", f"    return {p['jump']}();", "}"]
            if p.get("reserve"):
                out.append(f"RESERVE word {p['jsp_slot']}_space[{octal(p['reserve'])}];")
            return out
        if p.get("machine") == "start vectors":
            out = []
            for v in self.binds.starts:
                head.append(f"BLOCK void {v['network']}(void);")
                start = "START " if v.get("tape") else ""
                out += [f"AT({octal(v['at'])}) {start}BLOCK void vector_{v['network']}(void)", "{",
                        f"    return {v['network']}();", "}"]
            return out
        raise BindError(f"{self.path.name}: a place is a routine, fields, or a machine word: {p}")

    def compile(self) -> str:
        self.check_unstored()
        for p in self.spec["place"]:
            if "routine" in p:
                self.shift_homes(self.flat_routine(self.prog.routines[p["routine"]]))
        self.copied_kinds()
        body: list[str] = []
        head: list[str] = []
        for p in self.spec["place"]:
            if "routine" in p:
                for f in p.get("data", []):
                    if "." not in f or self.prog.records[f.split(".")[0]].count:
                        continue                # a copy's own word: declared below
                    if self.binds.held_place(f):
                        # a place held as code: the jump to it, to itself until it is set
                        head.append(f"insn {self.binds.c_name(f)} = I_JMP(&{self.binds.c_name(f)});")
                        continue
                    head.append(f"word {self.binds.c_name(f)} = {self.initial(f)};")
                body += self.routine(self.binds.bound[p["routine"]])
            elif "fields" in p:
                for f in p["fields"]:
                    if f in self.binds.held:
                        body.append(f"shift {self.binds.c_name(f)} = {self.shift_initial(f)};")
                    else:
                        body.append(f"word {self.binds.c_name(f)} = {self.initial(f)};")
            elif "slots" in p:
                body += self.slots(p)
            elif "store" in p:
                if self.store_of(p["store"]):
                    head.append(f"JSP void {self.store_of(p['store'])[0]}(register insn w);")
                    body += self.store_routine(p)
            elif "base" in p:
                d = p["base"]
                body.append(f"{self.word_type(d)} *{self.binds.c_name(d)}_base = {self.address(d, 0)};")
            elif "exit" in p:
                head.append(f"BLOCK void {p['exit']}(void);")
                body += [f"BLOCK void {p['exit']}(void)", "{", "}"]
            elif p.get("table"):
                body.append(self.table_words())
            elif "shifts" in p:
                f = p["shifts"]
                entries = ", ".join(self.code_word(f, octal(n)) for n in self.shift_table(f))
                body.append(f"shift {self.binds.c_name(f)}_shifts[{len(self.tables[f])}] = {{ {entries} }};")
            else:
                body += self.machine(p, head)
        templates = [line for f in sorted(self.run_fields) for line in self.run_templates(f)]
        head += [f"insn {w} = I_JMP(&{w});" for w in self.jump_words()]
        inline: list[str] = []
        done: set[str] = set()
        while todo := sorted(n for n in self.callees - done if self.binds.bound[n].convention == "INLINE"):
            for name in todo:
                done.add(name)
                inline = self.routine(self.binds.bound[name]) + inline
        for name in [p["routine"] for p in self.spec["place"] if "routine" in p] + sorted(self.callees - done):
            b = self.binds.bound[name]
            if name in self.binds.carried:
                # a jump through the homed word a walk carries a field's word into
                self.typedefs.add("typedef void block_code(void) BLOCK;")
                head.append(f"HOMED block_code *{name};")
                continue
            head.append(b.declaration() + ";")
            if b.block and b.unit == self.path:
                head.append(b.declaration(block=True) + ";")
        head = list(dict.fromkeys(head))
        head += [f"extern word {self.binds.c_name(f)};" for f in sorted(self.externs)]
        head += [f"ENTRY_CELL({self.binds.cell_of[f]}) word {'*' if f in self.binds.pointers else ''}"
                 f"{self.binds.c_name(f)};" for f in sorted(self.cells_used)]
        head += [self.pool_word(f) for f in sorted(set(self.spec.get("pool", [])) | self.pools_used)]
        head += [f"POOL word {name};" for name in sorted(self.pool_locals)]
        for name in sorted(self.named):
            if name in self.binds.bound:
                head.append(self.binds.bound[name].declaration() + ";")
            elif name in self.binds.jsp_slots:
                head.append(f"JSP {'io_word' if self.binds.jsp_slots[name]['returns'] == 'io' else 'word'} {name}(void);")
            else:
                raise BindError(f"{self.path.name}: a member's word names {name}, which no binding binds")
        piece_of = {name: d for d, pieces in self.binds.pieces.items() for _, _, name in pieces}
        head += [f"extern {self.word_type(piece_of[name]) if name in piece_of else 'word'} {name}[];"
                 for name in sorted(self.named_data)]
        head += [f"extern HOMED block_code *{into};" for into in sorted(self.carried)]
        head += [f"HOMED word *{c};" for c in sorted(self.homed)]
        head += [f"HOMED word *{self.binds.c_name(f)};" for f in sorted(self.homed_pointers)]
        head += [f"HOMED {self.word_type(into)} *{name};" for name, into in sorted(self.homed_locals.items())]
        head += [f"HOMED word {home};" for home in sorted(self.duff_homes)]
        head += self.copy_words()
        if stray := self.walk.get("stray"):
            head.append(f"POOL word *{stray['cursor']};")
        if self.cleared:
            head.append(f"HOMED word *{self.cleared} = 0;")
        head += self.held_elsewhere("\n".join(inline + body))
        head = sorted(self.typedefs) + list(dict.fromkeys(head))
        for f in sorted(self.kinds):
            name = self.binds.c_name(f)
            if self.binds.homes.get(f) == "table":
                head += [f"HOMED const shift *{name};", f"extern shift {name}_shifts[{len(self.shift_table(f))}];"]
            elif f not in self.binds.placed:
                # no data word: the instruction at its one use, run in place
                head.append(f"HOMED shift {name} = SHIFT_UNSET;")
        head += [self.templates[name] for name in sorted(self.templates)]
        return "\n".join(head + templates + inline + body) + "\n"


STORAGE = re.compile(r"[A-Za-z_]\w*(\.(hi|lo))?")


class Aliases(dict):
    """Function.alias: a name's C storage, told to record as it is set."""

    def __init__(self, record):
        super().__init__()
        self.record = record

    def __setitem__(self, key, value):
        self.record(key, value)
        super().__setitem__(key, value)

    def setdefault(self, key, value):
        if key not in self:
            self[key] = value
        return self[key]


class Function:
    """One C function's body from the RUNS statements it runs."""

    def __init__(self, unit: Unit, bound: Bound, own: dict[str, str], stmts: list):
        self.unit = unit
        self.binds = unit.binds
        self.b = bound
        self.own = own                          # field -> C parameter
        self.stmts = stmts
        self.out: list[str] = []
        self.tail: list[str] = []               # laid out after the body: see loop
        self.scopes: list[set[str]] = [set(own.values())]
        self.storage: dict[str, set[str]] = {}  # a C name -> the RUNS names compiled to it (Occupancy)
        self.alias: dict[str, str] = Aliases(self.stored_as)   # field or local -> C expression
        self.io_names = {leaf(f) if "." in f else f for f in bound.io | self.binds.io_fields}
        self.rest: list[list] = []              # what runs after the statement being compiled
        self.loops: list[tuple[str, str] | None] = []   # (break, continue) labels; None: a C loop
        self.labels = 0
        self.merged_head: tuple[object, str] | None = None
        self.results: dict[str, str] = {}       # callee -> its result's C local
        self.cursor_params = set(unit.prog.routines[bound.name].params)
        self.pending: tuple[str, str, int] | None = None    # (field, call, depth): a result in AC, see call
        self.consumed: tuple | None = None
        self.nested = 0
        self.top: list[str] = []                # declared at the function's top
        self.known: dict[str, int] = {}         # table-held field -> the count it holds here
        self.slot_maps: list[tuple[str, dict]] = []     # (slot variable, field -> cursor) of each walk
        self.resting: tuple[int, dict] | None = None    # the slot the cursors rest on after a walk
        self.held: dict = {}                    # a guard's read of a field, kept: key -> (C local, "ac"/"io")
        self.held_xor: tuple | None = None      # (field and member, C local, guards left) of a shared xor
        self.chained: dict[str, list[str]] = {} # a field holding a slot -> the fields whose cursors are set
        self.depth = 1                          # the depth of the statement being compiled
        self.has_table = any(x[0] == "if" and table_cases(x) for x in walk(stmts))
        self.heads: dict[int, tuple[str, int]] = {}  # id of a rotated loop -> (its second entry, statements)
        self.data_placed = False
        self.pulsed = False                     # a point of this routine has asked for a pulse
        self.duff: dict[int, tuple[str, str]] = {}  # id of a statement -> (jump home, local) to store after it
        self.duff_set: set[int] = set()         # ids of the counted loops whose jump is set
        self.returns_out = False                # the routine's last loop returns through its breaks
        self.preinc: str | None = None          # a homed local the next comparison steps first
        self.apart: list[dict] = []             # the loops laid out with their arms apart (apart_loop)
        self.exit_next = False                  # the next return is the routine's exit (guards)
        self.exit_label: str | None = None      # where the routine's exit lies, once laid out
        self.pair_halves(stmts)

    # ---- names

    def stored_as(self, name: str, text: str):
        """name, a field or a local of the RUNS, is compiled to the C text."""
        if STORAGE.fullmatch(text):
            self.storage.setdefault(text, set()).add(name)

    def label(self, what: str) -> str:
        self.labels += 1
        return f"{what}{self.labels}"

    def base(self, name: str) -> str:
        """A copy's own local as the Processor names it (Unit.own_copy)."""
        return self.unit.local_base.get(name, name)

    def place_local(self, e) -> str | None:
        """A local that holds a place in a collection: its base name."""
        return self.base(e[1]) if e[0] == "name" and self.base(e[1]) in self.b.into else None

    def cell(self, dotted: str) -> str:
        self.unit.cells_used.add(dotted)
        return self.binds.c_name(dotted)

    def own_result_local(self, dotted: str) -> bool:
        """A result held only in AC: a C local of this function."""
        return dotted in self.b.result and not self.binds.stored(dotted) and dotted not in self.binds.io_fields

    def place(self, dotted: str) -> str:
        text = self.where_is(dotted)
        self.stored_as(dotted, text)
        return text

    def where_is(self, dotted: str) -> str:
        if "sense" in self.binds.devices.get(dotted, {}):
            raise BindError(f"{self.b.name}: {dotted} is sense switch {self.binds.devices[dotted]['sense']}: "
                            f"a guard compares it with a member; it is no word to read")
        if dotted in self.binds.devices:
            return f"{self.binds.devices[dotted]['read']}()"
        if dotted in self.binds.addresses:
            if self.binds.addresses[dotted] != "after table":
                raise BindError(f"{dotted}: no address {self.binds.addresses[dotted]!r}")
            return self.binds.c_name(dotted)
        if self.pending and self.pending[0] == dotted and self.pending[2] == self.nested:
            self.consumed, self.pending = self.pending, None
            return self.consumed[1]
        if dotted in self.alias:
            return self.alias[dotted]
        if dotted in self.own:
            return self.own[dotted]
        if dotted in self.binds.io_fields or self.own_result_local(dotted) \
                or self.binds.in_register(dotted, self.unit.path):
            return leaf(dotted)
        if dotted in self.binds.pool:
            self.unit.pools_used.add(dotted)
            return self.binds.c_name(dotted)
        if self.binds.homes.get(dotted) == "pointer":
            self.unit.homed_pointers.add(dotted)
            return self.binds.c_name(dotted)
        if dotted in self.binds.cell_of:
            return self.cell(dotted)
        if dotted in self.binds.placed:
            if self.binds.placed[dotted] != self.unit.path:
                self.unit.externs.add(dotted)
            return self.binds.c_name(dotted)
        raise BindError(f"{self.b.name}: {dotted} has no place in the binding")

    def declared(self, name: str) -> bool:
        return any(name in s for s in self.scopes)

    # ---- expressions

    @staticmethod
    def constant(e) -> str:
        """An initial value: a number, or an expression of numbers, as its word."""
        if e[0] == "num":
            return octal(e[1])
        if e[0] == "neg" and e[1][0] == "num":
            return f"-{octal(e[1][1])}" if e[1][1] else "MINUS_ZERO"
        w = Function.constant_word(e).v
        return octal(w) if not w & runs.SIGN else "MINUS_ZERO" if w == runs.MASK else f"-{octal(w ^ runs.MASK)}"

    @staticmethod
    def constant_word(e) -> runs.W:
        if e[0] == "num":
            return runs.word_of(e[1])
        if e[0] == "neg":
            return runs.W(Function.constant_word(e[1]).v ^ runs.MASK)
        if e[0] == "bin" and e[1] in ("+", "-", "&", "|", "^", "<<", ">>"):
            return runs.binary(e[1], Function.constant_word(e[2]), Function.constant_word(e[3]))
        raise BindError(f"an initial value is a number: {e!r}")

    def expr(self, e) -> str:
        return self._expr(e)[0]

    def cursor(self, e) -> str:
        """`record.field[slot]`: through the cursor on the slot, when one
        points at it: the routine's own slot, a walk's, or the slot the
        cursors rest on after a walk. Else, for a slot by number, the word
        in the table. A cursor homed in this unit is read or written at its
        home the first time (or the first time inside the Processor that
        holds its home), and through it everywhere else."""
        d, slot, may_home = dotted_of(e[1]), e[2], len(e) == 4
        cursors = None
        if slot[0] == "name" and self.base(slot[1]) in self.b.homes and self.base(slot[1]) not in self.b.into:
            # a slot by index, added to the word of the collection's address into
            # the address field of the instruction that reads through it
            if d not in self.binds.bases:
                raise BindError(f"{self.b.name}: {slot[1]} indexes {d}: a place base = {d!r} lays out its address")
            at = f"{slot[1]}_at"
            if self.binds.bases[d] != self.unit.path:
                raise BindError(f"{self.b.name}: the word of {d}'s address is laid out in another unit")
            self.unit.homed_locals[at] = d
            self.emit(self.depth, f"{at} = {slot[1]} + {self.binds.c_name(d)}_base;")
            return f"*home({at})"
        if slot[0] == "name" and self.base(slot[1]) in self.b.homes:
            # a local held in the address field of the instruction that reads through it
            if self.b.into.get(self.base(slot[1])) != d:
                raise BindError(f"{self.b.name}: {slot[1]} holds a place in {self.b.into.get(self.base(slot[1]))}")
            if slot[1] not in self.unit.home_laid_out:
                self.unit.home_laid_out.add(slot[1])
                return f"*home({slot[1]})"
            return f"*{slot[1]}"
        if slot[0] == "num" and slot[1] in self.unit.slot_data.get(d, {}):
            return self.unit.slot_data[d][slot[1]]
        if slot[0] == "name" and slot[1] in self.cursor_params:
            cursors = self.binds.cursors
        elif slot[0] == "name":
            cursors = next((m for v, m in reversed(self.slot_maps) if v == slot[1]), None)
        elif slot[0] == "num" and self.resting and self.resting[0] == slot[1]:
            cursors = self.resting[1]
        elif slot[0] == "num" and self.binds.table:
            return f"{self.binds.table['at']}[{octal(self.binds.table_offset(d) + slot[1])}]"
        elif (held := dotted_of(slot)) in self.binds.slot_cursors:
            cursors = self.binds.slot_cursors[held]
            self.chain(held, d)
        elif self.binds.into.get(held) == d:
            # a field that holds a place in the collection holds its address
            p = self.place(held)
            if self.binds.homes.get(held) == "pointer" and held not in self.unit.home_laid_out:
                self.unit.home_laid_out.add(held)
                return f"*home({p})"
            return f"*{p}"
        if cursors is None or d not in cursors:
            raise BindError(f"{self.b.name}: no cursor for {e!r}")
        c = cursors[d]
        if c in self.unit.homed and c not in self.unit.home_kind \
                and (self.unit.homed[c] is None or may_home):
            self.unit.home_kind[c] = "laid out"
            return f"*home({c})"
        return f"*{c}"

    def chain(self, held: str, upto: str | None = None):
        """The cursors on the slot a field holds are set in the table's
        order, each from the one before: the first adds the field's slots
        to the index cursor's home word, the rest add them to the one
        before, which AC still holds. Set up to `upto`, or all of them."""
        cursors = self.binds.slot_cursors[held]
        order = self.table_order(cursors)
        done = self.chained.setdefault(held, [order[0]])
        if upto and upto not in order:
            raise BindError(f"{self.b.name}: no cursor for {upto} on the slot {held} holds ([cursors.\"{held}\"])")
        last = order.index(upto) if upto else len(order) - 1
        for n in range(len(done), last + 1):
            count = octal(self.unit.prog.records[order[n - 1].split(".")[0]].count)
            prev = cursors[order[n - 1]]
            text = f"{count} + {prev}" if n == 1 else f"{prev} + {count}"
            self.emit(self.depth, f"{cursors[order[n]]} = {text};")
            done.append(order[n])

    def slot_store(self, s, depth: int) -> bool:
        """A store into the slot a field holds. A plain value goes through
        IO, for AC holds the cursors' chain; before any other value the rest
        of the chain is set. A value that keeps the word's high bits and
        sets its address part is a dap."""
        _, target, e, _ = s
        held = dotted_of(target[2])
        d = dotted_of(target[1])
        cursors = self.binds.slot_cursors[held]
        if d in self.chained.get(held, [self.table_order(cursors)[0]]):
            plain = False
        else:
            plain = dotted_of(e) is not None or e[0] == "name"
            self.chain(held, d if plain else None)
        if e[0] == "bin" and e[1] == "|" and e[2][0] == "bin" and e[2][1] == "&" and e[2][2] == target \
                and e[2][3] == ("num", 0o770000) and e[3][0] == "num" and e[3][1] < 0o10000:
            word = self.cursor(target)
            word = f"home({word[6:-1]})" if word.startswith("*home(") else word[1:]
            self.emit(depth, f"{word}->addr = {octal(e[3][1])};")
            return True
        if plain:
            local = f"{leaf(d)}_io"
            self.emit(depth, f"register word {local} = {self.expr(e)};")
            self.emit(depth, f"{self.cursor(target)} = {local};")
            return True
        return False

    def member(self, enum: str, name: str) -> str:
        """An enum member as the word that spells it."""
        how = self.binds.spelled.get(enum, {}).get(name)
        if how is None:
            raise BindError(f"{self.b.name}: the binding spells no word for {enum} {name}")
        if isinstance(how, int):
            return octal(how)
        self.unit.named.add(how["routine"])
        if how.get("sign"):
            return f"{how['routine']} | (word){octal(runs.SIGN)}"
        return f"{how['routine']} | (word)0" if how.get("literal") else how["routine"]

    def _expr(self, e) -> tuple[str, int]:
        op = e[0]
        if op == "num":
            return octal(e[1]), 99
        if op == "member":
            word = self.member(e[1], e[2])
            return word, 3 if "|" in word else 99
        if op == "name":
            text = self.alias.get(e[1], e[1])
            self.stored_as(e[1], text)
            return text, 99
        if op == "field":
            if (d := dotted_of(e)) is None:
                raise BindError(f"cannot compile {e!r}")
            return self.place(d), 99
        if op == "index":
            return self.cursor(e), 99
        if op == "neg":
            if e[1] == ("num", 0):
                return "MINUS_ZERO", 99
            return f"-{self._paren(e[1], 11)}", 11
        if op == "bin" and e[1] in (">>", "<<") and self.binds.coded(count := dotted_of(e[3])):
            # shifted by the count a field holds: run the shift instruction that holds it
            return f"xct({self.shift_word(count)}, {self.expr(e[2])})", 99
        if op == "call" and e[1] in ("ral", "rar") and self.binds.coded(count := dotted_of(e[2][1])):
            return f"xct({self.shift_word(count)}, {self.expr(e[2][0])})", 99
        if op == "bin" and e[1] == ">>" and self.b.shifts == "xct":
            if e[3][0] != "num":
                raise BindError(f"{self.b.name}: a shift executed from a constant has a constant count")
            return f"xct(I_SAR({octal(e[3][1])}), {self.expr(e[2])})", 99
        if op == "bin" and e[1] in ("==", "!=") and (text := self.place_compare(e)) is not None:
            return text, C_LEVEL[e[1]]
        if op == "bin":
            _, o, a, b = e
            lvl = C_LEVEL[o]
            return f"{self._paren(a, lvl)} {C_OP.get(o, o)} {self._paren(b, lvl + 1)}", lvl
        if op == "call":
            return f"{e[1]}({', '.join(self.expr(a) for a in e[2])})", 99
        raise BindError(f"cannot compile {e!r}")

    def place_compare(self, e) -> str | None:
        """Two places in a collection compared, one held by a local the
        binding keeps in an instruction's address field, or in a data word,
        or by a field that holds an address. A homed local is compared as
        its home instruction (I_LIO(p), I_LIO(++p) when the step just before
        is taken here), a data local as the word it is, spelled as that
        instruction; a place by number as the same instruction at its
        address, or as its address against a field."""
        _, o, a, b = e
        sides = [a, b]
        kinds = [self.place_kind(x) for x in sides]
        if all(k is None or k == "number" for k in kinds):
            return None
        spelled = next((self.home_kind(x[1]) for x, k in zip(sides, kinds) if k == "homed"), None)
        data = [x[1] for x, k in zip(sides, kinds) if k == "data"]
        for name in data:
            if spelled:
                if self.unit.spellings.setdefault(name, spelled) != spelled:
                    raise BindError(f"{self.b.name}: {name} is compared as two instructions")
            spelled = self.unit.spellings.get(name)
            if spelled is None:
                raise BindError(f"{self.b.name}: {name} is compared before the home it is spelled as")
        texts = []
        for x, k in zip(sides, kinds):
            if k == "homed":
                step = "++" if self.preinc == x[1] else ""
                if step:
                    self.preinc = None
                texts.append(f"{spelled}({step}{x[1]})")
            elif k == "data":
                texts.append(x[1])
            elif k == "number":
                coll = next(self.b.into[self.base(y[1])] if y[0] == "name" else self.binds.into[dotted_of(y[1])]
                            for y, j in zip(sides, kinds) if j not in (None, "number"))
                text = self.unit.address(coll, self.fold(x))
                texts.append(f"{spelled}({text})" if spelled else text)
            else:
                texts.append(self.expr(x))
        return f"{texts[0]} {o} {texts[1]}"

    def place_kind(self, x) -> str | None:
        if (base := self.place_local(x)) is not None:
            return "homed" if base in self.b.homes else "data"
        if x[0] == "index" and dotted_of(x[1]) in self.binds.into:
            return "field"
        if x[0] == "num" or x[0] == "bin" and x[1] == "+" and x[2][0] == x[3][0] == "num":
            return "number"
        return None

    @staticmethod
    def fold(x) -> int:
        """A place by number: n, or n + k."""
        return x[1] if x[0] == "num" else x[2][1] + x[3][1]

    def home_kind(self, name: str) -> str:
        if name not in self.unit.home_kinds:
            raise BindError(f"{self.b.name}: {name} is compared before its home instruction is known")
        return self.unit.home_kinds[name]

    def place_value(self, local: str, e) -> str:
        """e as the value of a local that holds a place: a place by number
        is its address."""
        if self.place_kind(e) == "number":
            return self.unit.address(self.b.into[local], self.fold(e))
        return self.expr(e)

    def _paren(self, e, at_least: int) -> str:
        text, lvl = self._expr(e)
        return text if lvl >= at_least else f"({text})"

    def io_resident(self) -> set[str]:
        return self.io_names | {c for c in self.alias.values() if c.endswith(".lo")}

    def switch_test(self, e, negate: bool = False) -> str | None:
        """`field == m` for a field held in a sense switch or a program
        flag: the machine's test of it, `sense(n)` or `flag(n)`."""
        if e[0] != "bin" or e[1] not in ("==", "!=") or e[3][0] != "member":
            return None
        if e[2][0] == "name" and e[2][1] in self.b.flags:
            d, test = None, f"flag({self.b.flags[e[2][1]]})"
        elif (d := dotted_of(e[2])) is None:
            return None
        elif "sense" in self.binds.devices.get(d, {}):
            test = f"sense({self.binds.devices[d]['sense']})"
        elif d in self.binds.flags:
            test = f"flag({self.binds.flags[d]})"
        else:
            return None
        how = self.flag_word(e[3], d or e[2][1])
        holds = ((how == 1) == (e[1] == "==")) != negate
        return test if holds else f"!{test}"

    def flag_word(self, e, held: str) -> int:
        """The bit a member held in a sense switch or a program flag is."""
        how = self.binds.spelled.get(e[1], {}).get(e[2]) if e[0] == "member" else None
        if how not in (0, 1):
            raise BindError(f"{self.b.name}: {held} holds a member spelled 0 or 1, not {e!r}")
        return how

    def cond(self, e, negate: bool = False) -> str:
        if (text := self.switch_test(e, negate)) is not None:
            return text
        if negate:
            if e[0] != "bin" or e[1] not in NEGATED:
                raise BindError(f"cannot negate {e!r}")
            e = ("bin", NEGATED[e[1]], e[2], e[3])
        return self.expr(e)

    # ---- statements

    def emit(self, depth: int, text: str):
        self.out.append("    " * depth + text)

    def compile(self) -> list[str]:
        for f, text in self.own.items():
            self.stored_as(f, text)
        if self.b.exit_after:
            self.stmts = self.guards(self.stmts)
        if any(b.pulse and b.back == self.b.name for b in self.binds.bound.values()):
            self.emit(1, "ioh();")              # wait for the pulse the code that jumps here left pending
        self.block(self.stmts, 1, top=True)
        if self.tail:
            if not self.out or not self.out[-1].lstrip().startswith(("return", "goto")):
                raise BindError(f"{self.b.name}: code laid out after the body needs the body to end in a jump")
            self.out += self.tail
        return ["    " + line for line in self.top] + self.out

    def block(self, stmts: list, depth: int, top: bool = False):
        """A pending call result (see call) is taken up by the statement
        right after the call, or the call stands alone before it."""
        self.scopes.append(set())
        entries = {}
        for j, x in enumerate(stmts):
            if x[0] == "loop" and (m := self.rotated(stmts[:j], x)):
                entries[j - m] = self.heads[id(x)] = (self.label("enter"), m)
            for d in walk([x]):
                if (local := self.duff_bound(d)) is None or id(d) in self.duff_set:
                    continue
                sets = [k for k in range(j) if any(y[0] in ("let", "set") and y[1] == ("name", local)
                                                   for y in walk([stmts[k]]))]
                if sum(y[0] in ("let", "set") and y[1] == ("name", local) for y in walk(self.stmts)) \
                        != sum(y[0] in ("let", "set") and y[1] == ("name", local) for y in walk(stmts[:j])):
                    raise BindError(f"{d[-1]}: the jump into the loop's copies holds {local} as it is before "
                                    f"the loop: {local} is set only before it")
                if sets:
                    home = f"{self.b.name}_{local}"
                    self.unit.duff_homes.add(home)
                    self.duff[id(stmts[sets[-1]])] = (home, local)
                    self.duff_set.add(id(d))
        k = 0
        while k < len(stmts):
            if k in entries:
                self.emit(depth - 1, f"{entries[k][0]}:")
            before, mark = self.pending, len(self.out)
            self.rest.append(stmts[k + 1:])
            done = self.stmt(stmts, k, depth, top)
            self.rest.pop()
            if before is not None and self.consumed is not before:
                self.out.insert(mark, "    " * depth + before[1] + ";")
                if self.pending is before:
                    self.pending = None
            self.spill(stmts[k:k + done], stmts[k + done:], depth)
            for x in stmts[k:k + done]:
                if x[0] in ("let", "set"):
                    for name in (t[1] for t in (x[1][1] if x[1][0] == "tuple" else [x[1]]) if t[0] == "name"):
                        self.stored_as(name, self.alias.get(name, name))
            for x in stmts[k:k + done]:
                if id(x) in self.duff:
                    home, local = self.duff[id(x)]
                    self.emit(depth, f"{home} = {self.expr(('name', local))};")
            k += done
        if self.pending is not None and self.pending[2] == self.nested:
            self.emit(depth, self.pending[1] + ";")
            self.pending = None
        if top and falls_off(stmts) and not self.returns_out \
                and not self.out[-1].lstrip().startswith(("return", "goto")):
            self.emit(depth, self.return_text())
        self.scopes.pop()

    def spill(self, done: list, rest: list, depth: int):
        """An AC local the binding spills is kept in a pool word from its
        last set on, and read from there."""
        for name in self.b.spill - set(self.alias):
            sets = lambda stmts: any(x[0] in ("let", "set") and x[1] == ("name", name) for x in walk(stmts))
            if sets(done) and not sets(rest) and runs.mentions(rest, {name}):
                kept = f"{name}_kept"
                self.unit.pool_locals.add(kept)
                self.emit(depth, f"{kept} = {name};")
                self.alias[name] = kept

    def body(self, stmts: list, depth: int, head: list[str] = ()):
        self.emit(depth, "{")
        for line in head:
            self.emit(depth + 1, line)
        self.nested += 1
        self.block(stmts, depth + 1)
        self.nested -= 1
        self.emit(depth, "}")

    def declare_top(self, line: str):
        if line not in self.top:
            self.top.append(line)

    def ac_resident(self, text: str) -> bool:
        return text.endswith(".hi") or any(text in s for s in self.scopes) and text not in self.io_resident()

    def pair_halves(self, stmts: list):
        """A pair shifted by an executed shift instruction is one dword
        local, `pair`: xct returns the pair whole. Its two halves are that
        local's, through the whole function."""
        for s in walk(stmts):
            if s[0] in ("let", "set") and s[1][0] == "tuple" and s[2][0] == "call" \
                    and self.binds.coded(dotted_of(s[2][2][2])):
                for half, part in zip(s[2][2][:2], ("pair.hi", "pair.lo")):
                    key = dotted_of(half) or half[1]
                    if self.alias.setdefault(key, part) != part:
                        raise BindError(f"{s[-1]}: one pair is shifted by executed shifts")
                self.declare_top("dword pair;")

    def read_later(self, name: str) -> bool:
        names = {name}
        return any(runs.mentions(r, names) or self.mentions_field(r, name) for r in self.rest)

    def reads_target(self, e, target) -> bool:
        """e reads the place target names: the local, or the field at any slot."""
        base = target[1] if target[0] == "index" else target
        if base[0] == "name":
            return bool(runs.mentions(e, {base[1]}))
        return self.mentions_field(e, dotted_of(base))

    @staticmethod
    def mentions_field(tree, dotted: str) -> bool:
        if isinstance(tree, tuple) and tree and tree[0] == "field":
            return dotted_of(tree) == dotted
        if isinstance(tree, dict):
            tree = list(tree.values())
        return isinstance(tree, (list, tuple)) and any(Function.mentions_field(t, dotted) for t in tree)

    def return_text(self, value: str | None = None) -> str:
        if self.exit_label:
            return f"goto {self.exit_label};"   # the exit lies where guards put it
        if value is not None:
            return f"return {value};"
        if self.b.convention == "BLOCK" and self.unit.exit:
            # the unit's blocks leave through its shared exit
            return f"return {self.unit.exit}();"
        if self.b.convention == "BLOCK":
            # a firing ends here: the machine runs the frame again
            if "repeat" not in self.unit.spec:
                raise BindError(f"{self.b.name}: a block that runs off its end ends the firing: the unit names "
                                f"the Network the PDP-1 runs again (repeat), or its shared exit")
            return f"return {self.unit.spec['repeat']}();"
        res = [self.place(f) for f in self.b.result]
        if not res:
            return "return;"
        if len(res) == 1:
            return f"return {res[0]};"
        return f"return (dword){{ {res[0]}, {res[1]} }};"

    def lay_out(self, stmts: list, k: int, depth: int) -> int:
        """A member written into a collection held as a run of code, the
        fields its arm holds at the same slot, then the slot stepped on:
        the member's code stored at the slot (LAY_OUT), its holes filled
        with the fields' words."""
        s = stmts[k]
        f, slot, where = held_field(s[1]), s[1][2], s[-1]
        w = self.binds.walks[f]
        member = s[2][1] if s[2][0] == "name" else s[2][2] if s[2][0] == "member" else None
        if member not in w.arms:
            raise BindError(f"{where}: {f} holds a member whose arm the walk ({w.routine}) runs")
        values, j = {}, k + 1
        while j < len(stmts) and stmts[j][0] == "set" and stmts[j][1][0] == "index" and stmts[j][1][2] == slot \
                and held_field(stmts[j][1]).split(".")[0] == f.split(".")[0]:
            values[held_field(stmts[j][1])] = stmts[j][2]
            j += 1
        if j >= len(stmts) or self.incremented(stmts[j]) != slot:
            raise BindError(f"{where}: a member of {f} is written, then the slot it went to steps on")
        if set(values) != set(w.holds[member]):
            raise BindError(f"{where}: {member}'s arm holds {w.holds[member]}: the slot sets those, not "
                            f"{sorted(values)}")
        self.unit.run_fields.add(f)
        store = self.unit.store_of(f)
        if store:
            self.declare_top(f"register insn {store[1]};")
        jump = self.unit.jump_words(f)
        args = [self.place(dotted_of(slot)), f"{self.binds.c_name(f)}_{member}",
                *(store or ("0", "0")), jump[0] if jump else "0",
                *(self.expr(values[g]) for g in w.holds[member])]
        self.emit(depth, f"LAY_OUT({', '.join(args)});")
        return j - k + 1

    def incremented(self, s):
        """`set x = x + 1`: the place x, else None."""
        if s[0] == "set" and s[2][0] == "bin" and s[2][1] == "+" and s[2][3] == ("num", 1) \
                and s[2][2] == s[1]:
            return s[1]
        return None

    def one_instruction(self, s, nxt) -> str | None:
        """`set a = -a` on an AC local, then `set f = 0` on a place in IO:
        cma and cli, which the PDP-1 does as one instruction. Likewise a
        program flag set, then a new AC local set to 0: clf and cla."""
        if nxt and s[0] == "set" and dotted_of(s[1]) in self.binds.flags and nxt[0] == "let" \
                and nxt[1][0] == "name" and nxt[2] == ("num", 0) and nxt[1][1] not in self.b.io:
            name = nxt[1][1]
            self.declare_top(f"word {name};")
            self.scopes[0].add(name)
            flag = self.binds.flags[dotted_of(s[1])]
            how = self.flag_word(s[2], dotted_of(s[1]))
            return f"{'stf' if how else 'clf'}({flag}), {name} = 0;"
        if not (nxt and s[0] == nxt[0] == "set" and s[1][0] == "name" and s[2] == ("neg", s[1])
                and nxt[2] == ("num", 0) and nxt[1][0] != "tuple"):
            return None
        a, io = self.expr(s[1]), self.expr(nxt[1])
        if not self.ac_resident(a) or io not in self.io_resident():
            return None
        return f"{a} = -{a}, {io} = 0;"

    def clear_with_flag(self, stmts: list, k: int, depth: int) -> int | None:
        """A program flag set, then a new AC local and a new IO local set to
        0: one instruction (cla cli clf 6)."""
        s, *more = stmts[k:k + 3]
        flagged = s[0] in ("let", "set") and s[1][0] == "name" and s[1][1] in self.b.flags
        if not flagged or len(more) != 2 or any(x[0] != "let" or x[2] != ("num", 0) for x in more):
            return None
        (ac, io) = (more[0][1][1], more[1][1][1])
        if ac in self.b.io or io not in self.b.io:
            return None
        self.declare_top(f"word {ac};")
        self.declare_top(f"register word {io};")
        self.scopes[0] |= {ac, io}
        how = self.flag_word(s[2], s[1][1])
        self.emit(depth, f"{ac} = 0, {io} = 0, {'stf' if how else 'clf'}({self.b.flags[s[1][1]]});")
        return 3

    def duff_bound(self, s) -> str | None:
        """A counted loop from a local up to a number, that does not read its
        index: the local, else None."""
        if s[0] != "for" or s[2][0] != "name" or s[3][0] != "num" or runs.mentions(s[4], {s[1]}):
            return None
        return s[2][1]

    def duff_device(self, s, depth: int):
        """A counted loop from a local up to n is a jump into a run of n + 1
        copies of its body, past as many as the local says (Duff's device).
        The jump's address is set right after the local's last set before
        the loop (see block)."""
        _, _, lo, hi, body, where = s
        if id(s) not in self.duff_set:
            raise BindError(f"{where}: a jump into a run of the loop's bodies needs its start set before it")
        self.emit(depth, f"switch ((int){self.b.name}_{lo[1]})")
        self.emit(depth, "{")
        for k in range(hi[1] + 1):
            self.emit(depth, f"case {k}:")
            self.block(body, depth + 1)
        self.emit(depth, "}")

    def stmt(self, stmts: list, k: int, depth: int, top: bool) -> int:
        s = stmts[k]
        op = s[0]
        nxt = stmts[k + 1] if k + 1 < len(stmts) else None
        last = top and nxt is None
        self.depth = depth
        if op == "set" and s[1][0] == "index" and held_field(s[1]) in self.binds.walks:
            return self.lay_out(stmts, k, depth)
        if op == "set" and nxt and (pointer := self.through(s[1])) and self.incremented(nxt) == s[1][2]:
            # a word into the place a field holds, and the field steps on
            self.emit(depth, f"*{self.place(pointer)}++ = {self.expr(s[2])};")
            return 2
        if op == "stop":
            # the machine halts, and halts again each time it is continued
            self.emit(depth, "for (;;)")
            self.emit(depth + 1, "hlt();")
            return 1
        if op == "set" and (held := dotted_of(s[1])) in self.binds.slot_cursors:
            if s[2] != ("num", 0):
                raise BindError(f"{s[-1]}: {held} is a cursor: it starts at slot 0 and steps in a search")
            first = self.table_order(self.binds.slot_cursors[held])[0]
            offset = self.binds.table_offset(first)
            self.emit(depth, f"{self.binds.slot_cursors[held][first]} = {self.binds.table['at']}"
                             + (f" + {octal(offset)}" if offset else "") + ";")
            self.chained[held] = [first]
            return 1
        plain_store = op == "set" and s[1][0] == "index" and dotted_of(s[1][2]) in self.binds.slot_cursors \
            and (dotted_of(s[2]) is not None or s[2][0] == "name")
        for held, done in list(self.chained.items()):
            if 1 < len(done) < len(self.binds.slot_cursors[held]) and not plain_store:
                self.chain(held)                # AC is wanted for something else: finish the chain
        if op == "set" and s[1][0] == "index" and dotted_of(s[1][2]) in self.binds.slot_cursors \
                and self.slot_store(s, depth):
            return 1
        if op == "loop" and (search := self.search(s)) is not None:
            self.search_loop(s, search, depth)
            return 1
        if op == "slots":
            self.slots(s, depth)
            return 1
        if op == "dispatch":
            self.dispatch(s, depth)
            return 1
        if op == "cursors":
            self.set_cursors(depth)
            return 1
        if op == "clear":
            self.clear(depth)
            return 1
        if op == "wait":
            raise BindError(f"{s[-1]}: the binding waits only in the halt that shows a stream")
        if (target := self.incremented(s)) is not None and self.place_kind(target) == "homed" \
                and nxt and nxt[0] == "if" and nxt[1][0][0][0] == "bin" and nxt[1][0][0][1] in ("==", "!=") \
                and target in nxt[1][0][0][2:]:
            self.preinc = target[1]             # the comparison steps it (I_LIO(++p))
            return 1
        if op == "set" and nxt and nxt[0] == "set" and nxt[2] == s[2] and s[1][0] != "tuple" \
                and self.incremented(s) is None and not self.reads_target(s[2], s[1]) \
                and nxt[1][0] != "tuple" and not re.fullmatch(r"-?\w+", self.expr(s[2])):
            # One value stored in two places: loaded once, kept in AC. The
            # value must not read the first place, which the second set would
            # see changed.
            local = self.label("value")
            self.emit(depth, f"word {local} = {self.expr(s[2])};")
            self.scopes[-1].add(local)
            for x in (s, nxt):
                self.assign((x[0], x[1], ("name", local), x[3]), None, False, depth)
            return 2
        if (target := self.incremented(s)) is not None:
            text = self.expr(target)
            if text.startswith("*home("):
                raise BindError(f"{s[-1]}: the cursor's home is the first instruction that touches "
                                f"{dotted_of(target[1]) or target}, here; a home loads or stores, it does not step")
            if nxt and nxt[0] == "if" and len(nxt[1]) == 1 \
                    and nxt[1][0][0][0] == "bin" and nxt[1][0][0][2] == target and nxt[1][0][0][3] == ("num", 0):
                self.if_stmt(nxt, depth, f"++{text} {nxt[1][0][0][1]} 0")
                return 2
            self.emit(depth, f"++{text};")
            return 1
        if (n := self.clear_with_flag(stmts, k, depth)) is not None:
            return n
        if (text := self.one_instruction(s, nxt)) is not None:
            self.emit(depth, text)
            return 2
        if op in ("let", "set") and s[1][0] == "tuple":
            self.pair(s, depth)
            return 1
        if op == "let" and (rotated := self.rotated_operand(s)) is not None:
            # pdp1cc rotates a local in place: take the operand into the local first
            name = s[1][1]
            self.emit(depth, f"word {name} = {self.expr(rotated)};")
            self.scopes[-1].add(name)
            self.emit(depth, f"{name} = {self.expr(self.with_operand(s[2], name))};")
            return 1
        if op in ("let", "set") and s[1][0] == "name" and s[1][1] in self.b.flags:
            return self.flag(s[1][1], s[2], depth)
        if op == "data_here":
            self.emit(depth, f"PLACE({', '.join(s[1])});")
            return 1
        if op == "exit_next":
            self.exit_next = True
            return 1
        if op in ("let", "set") and (local := self.place_local(s[1])) is not None and self.incremented(s) is None:
            value = self.place_value(local, s[2])
            if local in self.b.homes and s[1][1] not in self.unit.local_base:
                # the routine is laid out once: its home is one word of the unit
                self.unit.homed_locals[s[1][1]] = self.b.into[local]
            self.emit(depth, f"{s[1][1]}{'' if local in self.b.homes else '.addr'} = {value};")
            return 1
        if op == "let":
            name = s[1][1]
            if name in self.b.io and (held := self.expr(s[2])) in self.io_resident():
                self.alias[name] = held             # already in IO: no move
                return 1
            if name in self.alias or name in self.b.pool:
                self.emit(depth, f"{self.alias.get(name, name)} = {self.expr(s[2])};")
                return 1
            if self.declared(name):             # a let of another Processor laid out in this function
                self.emit(depth, f"{name} = {self.expr(s[2])};")
                return 1
            if self.apart:
                # the loop's labels may not precede a declaration: declared at the top
                self.declare_top(f"{'register word' if name in self.b.io else 'word'} {name};")
                self.scopes[0].add(name)
                self.emit(depth, f"{name} = {self.expr(s[2])};")
                return 1
            self.emit(depth, f"{'register word' if name in self.b.io else 'word'} {name} = {self.expr(s[2])};")
            self.scopes[-1].add(name)
            return 1
        if op == "emit":
            return self.display(s, nxt, depth)
        if op == "goto":
            self.emit(depth, f"goto {s[1]};")
            return 1
        if op == "label":
            self.emit(depth, f"{s[1]}:")
            self.known.clear()
            return 1
        if op == "set":
            return self.assign(s, nxt, last, depth)
        if op == "call":
            self.call(s, last, depth)
            return 1
        if op == "for" and self.duff_bound(s) is not None:
            self.duff_device(s, depth)
            return 1
        if op == "for":
            _, var, lo, hi, body, where = s
            if lo[0] != "num" or hi[0] != "num" or runs.mentions(body, {var}):
                raise BindError(f"{where}: a counted loop has constant bounds and does not read its index")
            self.emit(depth, f"for (int i = 0; i < {octal(hi[1] - lo[1] + 1)}; i++)")
            self.loops.append(None)
            self.body(body, depth)
            self.loops.pop()
            return 1
        if op == "args_done":
            self.emit(depth, "ARGS_DONE();")
            return 1
        if op == "load_io":
            if store := self.unit.store_of(s[1]):
                self.declare_top(f"register insn {store[1]};")
                self.emit(depth, f"{store[1]} = REPEATED({store[0]});")
            return 1
        if op == "leave":
            # out of the walk: to the routine the Network runs after it
            back = self.binds.after_walk(self.b.name)
            self.unit.named.add(back)
            self.emit(depth, f"return {back}();")
            return 1
        if op == "held_jump":
            self.emit(depth, f"HELD({self.binds.c_name(s[1])});")
            return 1
        if op == "loop" and self.b.arms == "apart":
            return self.apart_loop(s, nxt, depth)
        if op == "loop":
            if self.b.loops == "exit first":
                self.loop(s, depth)
            elif self.exits_last(s[2]):
                self.bottom_loop(s, depth, last)
            elif self.rotated([], s) is not None:
                self.rotated_loop(s, depth, last)
            else:
                # a loop that ends the routine leaves it through its breaks
                self.emit(depth, "for (;;)")
                self.loops.append((None, None) if last else None)
                self.returns_out = last
                self.body(s[2], depth)
                self.loops.pop()
            return 1
        if op == "if" and table_cases(s):
            self.jump_table(s, depth)
            return 1
        if op == "if" and self.apart and s[2] and not self.ends_in_jump(s[1][0][1]):
            self.apart_if(s, stmts, k, depth)
            return 1
        if op == "if":
            _, arms, other, _ = s
            if self.b.loops == "exit first" and nxt and nxt[0] == "loop" and len(arms) == 1 and not other \
                    and len(arms[0][1]) == 1 and nxt[2] and nxt[2][-1][:-1] == arms[0][1][0][:-1]:
                head = self.label("loop")
                self.merged_head = (nxt, head)
                self.emit(depth, f"if ({self.cond(arms[0][0])})")
                self.body(arms[0][1], depth, head=[f"{head}:"])
                return 1
            if (pair := self.xor_test(arms[0][0])) and len(arms) == 1 and not other and nxt \
                    and nxt[0] == "if" and self.xor_test(nxt[1][0][0]) and \
                    self.xor_test(nxt[1][0][0])[:2] == pair[:2]:
                # Two guards on one comparison: one xor, kept in AC.
                local = self.label("guard")
                self.emit(depth, f"word {local} = {pair[1]} ^ {self.expr(pair[0])};")
                self.scopes[-1].add(local)
                self.held_xor = (pair[:2], local, 2)
            self.if_stmt(s, depth)
            return 1
        if op in ("break", "continue"):
            labels = self.loops[-1] if self.loops else None
            if labels is None:
                self.emit(depth, f"{op};")
            elif op == "break" and labels[0] is None:
                self.emit(depth, self.return_text())        # the loop ends the routine
            elif op == "continue" and labels[1] is None:
                self.emit(depth, "continue;")
            else:
                self.emit(depth, f"goto {labels[0 if op == 'break' else 1]};")
            return 1
        if op == "return":
            if self.exit_next:
                self.exit_label, self.exit_next = self.label("exit"), False
                self.emit(depth - 1, f"{self.exit_label}:")
                self.emit(depth, "return;")
            else:
                self.emit(depth, self.return_text())
            return 1
        raise BindError(f"{s[-1]}: cannot compile {op}")

    @staticmethod
    def rotated_operand(s):
        """`let v = ...rar(e, n)...` with e not a name: e, else None."""
        for x in walk_expr(s[2]):
            if x[0] == "call" and x[1] in ("ral", "rar") and x[2][0][0] != "name":
                return x[2][0]
        return None

    @staticmethod
    def with_operand(e, name: str):
        if isinstance(e, tuple) and e and e[0] == "call" and e[1] in ("ral", "rar") and e[2][0][0] != "name":
            return ("call", e[1], [("name", name), *e[2][1:]])
        if isinstance(e, tuple):
            return tuple(Function.with_operand(x, name) if isinstance(x, (tuple, list)) else x for x in e)
        if isinstance(e, list):
            return [Function.with_operand(x, name) for x in e]
        return e

    # ---- the table and its cursors

    def table_order(self, cursors: dict) -> list[str]:
        return [f for f in self.binds.table_fields() if f in cursors]

    def set_cursors(self, depth: int):
        """Every cursor on the first slot: one pointer, stepped from the
        table's start by each field's slots, in the table's order."""
        table = self.binds.table["at"]
        fields = self.table_order(self.binds.cursors)
        self.emit(depth, f"word *cursor = {table};")
        for n, f in enumerate(fields):
            if n:
                count = self.unit.prog.records[fields[n - 1].split(".")[0]].count
                self.emit(depth, f"cursor = cursor + {octal(count)};")
            self.emit(depth, f"{self.binds.cursors[f]} = cursor;")

    def slots(self, s, depth: int):
        """A walk over the table's slots. The walk from slot 0 uses the
        cursors set at the frame's start; a walk from a slot after another
        walk's sets its own cursors one past that walk's, and loads what
        the binding carries. Each cursor steps on in the table's order, a
        stray cursor with them; the index cursor steps last and is tested
        against its home instruction one slot past the last."""
        _, var, lo, hi, body, where = s
        walk = self.unit.walk
        if hi[0] != "num":
            raise BindError(f"{where}: a walk over the slots ends at a slot by number")
        if lo == ("num", 0):
            cursors, outer = self.binds.cursors, True
            self.check_carry(body, where)
        elif lo[0] == "bin" and lo[1] == "+" and lo[2][0] == "name" and lo[3][0] == "num" and self.slot_maps:
            outer_var, outer_cursors = self.slot_maps[-1]
            if lo[2][1] != outer_var:
                raise BindError(f"{where}: a walk starts past the walk it is in")
            cursors, outer = walk["other"], False
            for f in self.table_order(cursors):
                self.emit(depth, f"{cursors[f]} = {octal(lo[3][1])} + {outer_cursors[f]};")
            for into in walk.get("carry", []):
                f = self.carried_field(into)
                self.unit.typedefs.add("typedef void block_code(void) BLOCK;")
                self.unit.carried[into] = f
                read = self.cursor(("index", as_field(f), ("name", outer_var)))
                self.emit(depth, f"{into} = (block_code *){read};")
        else:
            raise BindError(f"{where}: a walk starts at slot 0 or one past another walk's slot")
        index = walk["index"]
        top = self.label("slot")
        self.emit(depth, f"{top}:")
        self.slot_maps.append((var, cursors))
        self.block(body, depth)
        self.slot_maps.pop()
        steps = [f for f in self.table_order(cursors) if f != index]
        stray = walk.get("stray") if outer else None
        for f in steps:
            self.emit(depth, f"++{cursors[f]};")
            if stray and stray["after"] == f:
                self.emit(depth, f"++{stray['cursor']};")
        c = cursors[index]
        if self.unit.home_kind.get(c) != "LAC":
            raise BindError(f"{where}: the index cursor {c} has no home in a guard of this walk")
        past = self.binds.table_offset(index) + hi[1] + 1
        self.emit(depth, f"if (I_LAC(++{c}) != I_LAC({self.binds.table['at']} + {octal(past)}))")
        self.emit(depth + 1, f"goto {top};")
        if outer:
            self.resting = (hi[1] + 1, cursors)

    def carried_field(self, into: str) -> str:
        """The field whose word a walk carries into the homed jump into
        code a collection holds: the one the walker starts from at its slot
        (draw_outline: let at = ships.outline[slot]), which holds its place
        in that code."""
        b, r = self.binds.bound.get(into), self.unit.prog.routines.get(into)
        if b is None or not b.code:
            raise BindError(f"{self.unit.path.name}: [walk] carry: {into} is no [[code]] routine")
        w = next(w for w in self.binds.walks.values() if w.routine == into)
        index, where = w.start, w.where
        if not (r.params and index[0] == "index" and index[2] == ("name", r.params[0])):
            raise BindError(f"{where}: {into}'s jump is carried by the walk only through a field at its slot")
        f = dotted_of(index[1])
        if f not in self.binds.cursors or self.binds.into.get(f) != w.field:
            raise BindError(f"{where}: {into} starts from {f}, which holds no place in {w.field} "
                            f"the walk's cursors reach ([cursors], [into])")
        return f

    def check_carry(self, body: list, where: str):
        """A walk carries a jump's word as the walk from the slot after this
        one begins (mot); the RUNS reads it at the jump. They agree only when
        every slot whose calc reaches the jump has run that walk earlier in
        the same pass, and nothing the slot's rules run writes the field."""
        carry = self.unit.walk.get("carry", [])
        if not carry:
            return
        prog = self.unit.prog
        walks, sites = [], []

        def visit(stmts, guards, pos):
            for k, s in enumerate(stmts):
                here = pos + (k,)
                if s[0] == "slots":
                    walks.append((here, guards))
                elif s[0] == "if":
                    taken = []
                    for c, b in s[1]:
                        visit(b, guards + taken + [(c, True)], here)
                        taken.append((c, False))
                    visit(s[2], guards + taken, here)
                elif s[0] == "loop":
                    visit(s[2], guards + [(None, True)], here)
                elif s[0] in ("dispatch", "call"):
                    sites.append((here, guards, s))
        visit(body, [], ())

        def plain(e):
            return e[:3] if isinstance(e, tuple) and e[:1] == ("index",) else e

        def value(c, e, member):
            """The guard c when the field e holds member; None: undecided."""
            if c[0] == "bin" and c[1] in ("and", "or"):
                a, b = value(c[2], e, member), value(c[3], e, member)
                if c[1] == "and":
                    return False if False in (a, b) else None if None in (a, b) else True
                return True if True in (a, b) else None if None in (a, b) else False
            if c[0] == "not":
                v = value(c[1], e, member)
                return None if v is None else not v
            if c[0] == "bin" and c[1] in ("==", "!=") and plain(c[2]) == plain(e) and c[3][0] == "member" \
                    and member is not None:
                return (c[3][2] == member) == (c[1] == "==")
            return None

        for into in carry:
            f = self.carried_field(into)
            jump_at = prog.routines[into].body[0][-1]
            if f.split(".")[0] in prog.routines[into].writes:
                raise BindError(f"{jump_at}: {into} may write {f.split('.')[0]}, whose {f} the walk carries")
            for here, guards, s in sites:
                targets = s[3] if s[0] == "dispatch" else [s[1]]
                for t in targets:
                    if into not in runs.fires(prog, t, set()):
                        continue
                    member = None
                    if s[0] == "dispatch":
                        enum = field_type(prog, plain(s[1]))
                        member = next((m for m, how in self.binds.spelled.get(enum, {}).items()
                                       if isinstance(how, dict) and how.get("routine") == t), None)
                    e = s[1] if s[0] == "dispatch" else None
                    if not any(pos < here and all(g in guards or (g[0] is not None and value(g[0], e, member) == g[1])
                                                  for g in wguards) for pos, wguards in walks):
                        raise BindError(
                            f"{jump_at}: {into} jumps through {f} at its slot, which the binding loads as the walk "
                            f"from the slot after it begins ([walk] carry); a slot whose calc is {member or t} "
                            f"reaches the jump ({s[2] if s[0] == 'dispatch' else s[-1]}) without that walk "
                            f"({where})")
            fired = set().union(set(), *(runs.fires(prog, t, set())
                                         for _, _, s in sites for t in (s[3] if s[0] == "dispatch" else [s[1]])))
            stmts = list(walk(body)) + [x for r in sorted(fired) for x in walk(prog.routines[r].body)]
            if written := [s for s in stmts if s[0] == "set" and s[1][0] != "tuple"
                           and dotted_of(s[1][1] if s[1][0] == "index" else s[1]) == f]:
                raise BindError(f"{written[0][-1]}: this writes {f}, which the walk carries to {into}'s jump "
                                f"before the slot's calc runs ([walk] carry)")

    def search(self, s):
        """A loop that steps a field holding a slot and stops when it
        reaches a slot by number: (the field, that slot), else None."""
        body = s[2]
        if len(body) < 2 or body[-1][0] != "if" or len(body[-1][1]) != 1 or body[-1][2]:
            return None
        c = body[-1][1][0][0]
        held = dotted_of(c[2]) if c[0] == "bin" and c[1] == "==" else None
        if held not in self.binds.slot_cursors or c[3][0] != "num" or self.incremented(body[-2]) != c[2]:
            return None
        return held, c[3][1]

    def search_loop(self, s, search, depth: int):
        """The search: the loop's body, then one index of the cursor and a
        test of its home instruction against the one past the last slot
        (idx; sas; jmp), and what the loop runs when it gets there."""
        held, end = search
        body = s[2]
        cursors = self.binds.slot_cursors[held]
        first = self.table_order(cursors)[0]
        top, after = self.label("search"), self.label("found")
        self.emit(depth, f"{top}:")
        self.loops.append((after, top))
        self.block(body[:-2], depth)
        self.loops.pop()
        c = cursors[first]
        kind = self.unit.home_kind.get(c)
        if kind not in ("LAC",):
            raise BindError(f"{s[-1]}: the search's cursor {c} has no home in a guard of its loop")
        past = self.binds.table_offset(first) + end
        self.emit(depth, f"if (I_{kind}(++{c}) != I_{kind}({self.binds.table['at']} + {octal(past)}))")
        self.emit(depth + 1, f"goto {top};")
        self.block(body[-1][1][0][1], depth)
        self.emit(depth, f"{after}:")
        self.chained[held] = [first]

    def dispatch(self, s, depth: int):
        """A jump through the routine word, to the calc routine it names. A
        field in a pool word is a call through it (jsp i), whose result is
        the one every routine it may name returns."""
        _, e, where, targets = s
        if dotted_of(e) in self.binds.pool:
            results = {tuple(self.binds.bound[n].result) for n in targets}
            if len(results) != 1:
                raise BindError(f"{where}: the routines a pool word names return different results")
            (result,) = results
            call = f"{self.place(dotted_of(e))}()"
            if len(result) == 1 and result[0] in self.binds.io_fields:
                self.emit(depth, f"register word {leaf(result[0])} = {call};")
            elif result:
                raise BindError(f"{where}: a call through a pool word returns in IO")
            else:
                self.emit(depth, f"{call};")
            return
        self.unit.typedefs.add("typedef void jsp_routine(void) JSP;")
        key = repr(e)
        held = self.held.pop(key, None)
        word = held[0] if held and held[1] == "ac" else self.expr(e)
        self.emit(depth, f"((jsp_routine *){word})();")

    def clear(self, depth: int):
        """Every word of the table set to 0, by a cursor homed in the dzm."""
        if "clear" not in self.binds.table:
            raise BindError(f"{self.b.name}: the clearing loop's cursor is [table] clear")
        c, table = self.binds.table["clear"], self.binds.table["at"]
        top = self.label("clear")
        self.unit.cleared = c
        self.emit(depth, f"{c} = {table};")
        self.emit(depth, f"{top}:")
        self.emit(depth, f"*home({c}) = 0;")
        self.emit(depth, f"if (I_DZM(++{c}) != I_DZM({table} + {octal(self.binds.table_size())}))")
        self.emit(depth + 1, f"goto {top};")

    def if_stmt(self, s, depth: int, first: str | None = None):
        """An if, its first condition already compiled when `first` is
        given. When the else arm ends in an if whose arm ends with the
        statements of the first arm, those are laid out once, there, and
        the first arm jumps to them. A guard of and and or is laid out as
        jumps. When an arm ends in a jump, what follows the if is its else."""
        _, arms, other, where = s
        if len(arms) == 1 and other and (merged := self.shared_tail(other, arms[0][1])) is not None:
            label, rest = merged
            self.emit(depth, f"if ({first or self.cond(arms[0][0])})")
            self.body([("goto", label, where)], depth)
            self.block(rest, depth)
            return
        if first is None and len(arms) == 1 and self.compound(arms[0][0]) and self.enum_test(arms[0][0]) is None:
            self.jumping(s, depth)
            return
        before, ends = dict(self.known), []
        for n, (c, body) in enumerate(arms):
            head = []
            text = first if first and not n else self.guard(c, body, depth, head)
            self.emit(depth, f"{'else ' if n else ''}if ({text})")
            self.known = dict(before)
            self.body(body, depth, head)
            ends.append(self.known)
        self.known = dict(before)
        if other and len(arms) == 1 and self.ends_in_jump(arms[0][1]):
            self.block(other, depth)
            ends.append(self.known)
        elif other:
            self.emit(depth, "else")
            self.body(other, depth)
            ends.append(self.known)
        self.known = {f: v for f, v in before.items() if all(end.get(f) == v for end in ends)}

    def ends_in_jump(self, stmts: list) -> bool:
        """Control cannot run past the statements: they end in a return, a
        goto, or a run of a block, which the PDP-1 jumps to."""
        if not stmts:
            return False
        x = stmts[-1]
        if x[0] in ("return", "goto"):
            return True
        if x[0] == "call":
            return self.binds.bound[x[1]].convention == "BLOCK"
        if x[0] == "if":
            return bool(x[2]) and all(self.ends_in_jump(b) for b in [b for _, b in x[1]] + [x[2]])
        return False

    @staticmethod
    def compound(c) -> bool:
        return c[0] == "bin" and c[1] in ("and", "or")

    def enum_test(self, c):
        """A guard on one enum field that the words of its members decide by
        sign and zero alone: (the field, the C test of its word against 0).
        `!= m` for every member spelled 0 is `!= 0`; for every member
        spelled with the sign bit, `>= 0`; for both, `> 0`. `== m` for the
        member spelled 0 is `== 0`."""
        terms, stack = [], [c]
        while stack:
            t = stack.pop()
            if t[0] == "bin" and t[1] == "and":
                stack += [t[3], t[2]]
            else:
                terms.append(t)
        place = terms[0][2] if terms[0][0] == "bin" else None
        enum = None
        for t in terms:
            if t[0] != "bin" or t[1] not in ("==", "!=") or t[2] != place or t[3][0] != "member":
                return None
            enum = t[3][1]
        spelled = self.binds.spelled.get(enum, {})
        zero = {m for m, how in spelled.items() if how == 0}
        sign = {m for m, how in spelled.items() if isinstance(how, dict) and how.get("sign")}
        members = {t[3][2] for t in terms}
        if len(terms) == 1 and terms[0][1] == "==":
            return (place, "== 0") if members == zero else None
        if any(t[1] != "!=" for t in terms):
            return None
        return {frozenset(zero): (place, "!= 0"), frozenset(sign): (place, ">= 0"),
                frozenset(zero | sign): (place, "> 0")}.get(frozenset(members))

    def xor_test(self, c):
        """`field == m` or `!=` for a member spelled as an address: (the
        field, the member's word, the C test of their xor against 0)."""
        if c[0] != "bin" or c[1] not in ("==", "!=") or c[3][0] != "member" or self.switch_test(c) is not None:
            return None
        if self.enum_test(c) is not None:
            return None
        return c[2], self.member(c[3][1], c[3][2]), f"{c[1]} 0"

    def guard(self, c, body: list, depth: int, head: list[str]) -> str:
        """The C condition of a guard. A guard that tests an enum field by
        sign and zero reads the field into a local first, and keeps it for
        the arm's next guard or jump through it: in AC when that comes
        first, else moved to IO (swap), past what the arm runs before it."""
        if (text := self.switch_test(c)) is not None:
            return text
        if (pair := self.xor_test(c)) is not None:
            held = self.held_xor
            if held and held[0] == pair[:2]:
                self.held_xor = (held[0], held[1], held[2] - 1) if held[2] > 1 else None
                return f"{held[1]} {pair[2]}"
            return f"({pair[1]} ^ {self.expr(pair[0])}) {pair[2]}"
        if (test := self.enum_test(c)) is None:
            sign_test = c[0] == "bin" and c[1] in ("<", ">=") and c[3] == ("num", 0)
            for d in sorted(self.b.io_reads):
                if sign_test and c[2][0] == "index" and dotted_of(c[2][1]) == d:
                    # IO tests only the sign (spi)
                    local = f"{self.binds.c_name(d)}_io"
                    self.emit(depth, f"register word {local} = {self.cursor(c[2])};")
                    return f"{local} {c[1]} 0"
                if sign_test and self.mentions_field(c, d):
                    local = f"{self.binds.c_name(d)}_io"
                    self.emit(depth, f"register word {local} = {self.place(d)};")
                    self.alias[d] = local
            text = self.cond(c)
            for d in self.b.io_reads:
                self.alias.pop(d, None)
            return text
        place, against = test
        key = repr(place)
        if key in self.held:
            local, _ = self.held.pop(key)
            return f"{local} {against}"
        local = self.label(place[1][2] if place[0] == "index" else leaf(dotted_of(place)))
        read = self.expr(place)
        if read.startswith("*home("):
            self.unit.home_kind[read[6:-1]] = "LAC"
        self.emit(depth, f"word {local} = {read};")
        self.scopes[-1].add(local)
        nxt = next((j for j, x in enumerate(body) if self.reads(x, key)), None)
        if nxt == 0 and body[0][0] == "dispatch":
            self.held[key] = (local, "ac")
        elif nxt is not None and body[nxt][0] == "if":
            if self.unit.spec.get("moves") != "swap":
                raise BindError(f"{self.b.name}: the binding moves no value from AC to IO")
            head.append(f"register word {local}_io = SWAP({local});")
            self.held[key] = (f"{local}_io", "io")
        return f"{local} {against}"

    def reads(self, x, key: str) -> bool:
        """x is a jump through the field, or a guard on it."""
        if x[0] == "dispatch":
            return repr(x[1]) == key
        if x[0] == "if":
            test = self.enum_test(x[1][0][0])
            return test is not None and repr(test[0]) == key
        return False

    def jumping(self, s, depth: int):
        """An if whose guard joins tests with and and or: each test jumps to
        the arm it decides, the last falls into the first arm. A sign test
        that jumps on its failure keeps its own skip, with the i bit
        flipped (SKIPNOT)."""
        _, ((c, body),), other, where = s
        yes, no = self.label("then"), self.label("else")
        used: set[str] = set()

        def test(e, negate: bool) -> str:
            if (text := self.switch_test(e, negate)) is not None:
                return text
            if (pair := self.xor_test(e)) is not None:
                op = NEGATED[pair[2][:2].strip()] if negate else pair[2][:2].strip()
                return f"({pair[1]} ^ {self.expr(pair[0])}) {op} 0"
            if e[0] == "bin" and e[1] in ("<", ">=") and e[3] == ("num", 0) and negate:
                return f"SKIPNOT({self.cond(e, negate=True)})"
            return self.cond(e, negate=negate)

        def jumps(e, falls: bool):
            """falls: the test after e, or the first arm, runs when e holds."""
            if e[0] == "bin" and e[1] in ("and", "or"):
                jumps(e[2], e[1] == "and")
                jumps(e[3], falls)
            elif falls:
                self.emit(depth, f"if ({test(e, True)})")
                self.emit(depth + 1, f"goto {no};")
                used.add(no)
            else:
                self.emit(depth, f"if ({test(e, False)})")
                self.emit(depth + 1, f"goto {yes};")
                used.add(yes)

        jumps(c, True)
        if yes in used:
            self.emit(depth - 1, f"{yes}:")
        self.block(body, depth)
        if other:
            if not self.ends_in_jump(body):
                raise BindError(f"{where}: the first arm of a jumping guard ends in a jump")
            self.emit(depth - 1, f"{no}:")
            self.block(other, depth)
        elif no in used:
            self.emit(depth - 1, f"{no}: ;")

    def shared_tail(self, stmts: list, tail: list):
        """stmts with `tail`, where it ends the last arm of its last if,
        labelled; None when it does not end there."""
        last = stmts[-1] if stmts else None
        if not last or last[0] != "if" or len(last[1]) != 1 or last[2]:
            return None
        (c, body), where = last[1][0], last[3]
        if len(body) >= len(tail) and body[len(body) - len(tail):] == tail:
            label = self.label("tail")
            inner = body[:len(body) - len(tail)] + [("label", label, where)] + tail
        elif (deeper := self.shared_tail(body, tail)) is not None:
            label, inner = deeper
        else:
            return None
        return label, stmts[:-1] + [("if", [(c, inner)], [], where)]

    def through(self, target) -> str | None:
        """`c[p]` with p a field that holds a place in c: p, else None."""
        if target[0] != "index" or (p := dotted_of(target[2])) is None:
            return None
        return p if self.binds.into.get(p) == dotted_of(target[1]) else None

    def rotated(self, before: list, s) -> int | None:
        """A loop whose body ends in `if c: X` with no else, X not leaving
        the loop: how many of the statements just before the loop X ends
        with (0 when none; None for another shape). Those are laid out once,
        before the loop, and X jumps back to them: the loop's second entry."""
        last = s[2][-1] if s[2] else None
        if not last or last[0] != "if" or len(last[1]) != 1 or last[2] or breaks(last[1][0][1]):
            return None
        arm = last[1][0][1]
        m = 0
        while m < min(len(arm), len(before)) and arm[len(arm) - 1 - m] == before[len(before) - 1 - m]:
            m += 1
        return m

    def rotated_loop(self, s, depth: int, last: bool):
        """The body, then the last if's test negated, jumping back to the
        top; then its arm, and a jump to the loop's second entry or its top.
        A step of the tested field just before the test is one index-and-
        skip (isp). A break of a loop that ends the routine is its return."""
        _, _, body, where = s
        *rest, end = body
        (c, arm), = end[1]
        head, m = self.heads.get(id(s), (None, 0))
        top = self.label("loop")
        after = None if last else self.label("after")
        self.emit(depth - 1, f"{top}:")
        self.loops.append((after, top))
        if rest and c[0] == "bin" and c[1] in NEGATED and c[3] == ("num", 0) \
                and self.incremented(rest[-1]) == c[2]:
            self.block(rest[:-1], depth)
            test = f"++{self.expr(c[2])} {NEGATED[c[1]]} 0"
        else:
            self.block(rest, depth)
            test = self.cond(c, negate=True)
        self.emit(depth, f"if ({test})")
        self.emit(depth + 1, f"goto {top};")
        self.block(arm[:len(arm) - m], depth)
        self.emit(depth, f"goto {head or top};")
        self.loops.pop()
        if after:
            self.emit(depth - 1, f"{after}: ;")

    def jump_table(self, s, depth: int):
        """An if-chain over 0..n is a jump table (switch). The arm of n lies
        in the table and ends in a jump. The other arms lie apart: the first
        right after the table, falling into the code after the chain; the
        rest after the routine's code, each jumping back. Data words the
        binding lays out inside the routine lie after the table, where
        control cannot reach."""
        value, arms = table_cases(s)
        n = sum(len(numbers) for numbers, _ in arms) - 1
        arm_of = {k: a for a, (numbers, _) in enumerate(arms) for k in numbers}
        inline = arm_of[n]
        if not self.ends_in_exit(arms[inline][1]):
            raise BindError(f"{s[-1]}: the last case of a jump table ends in a jump")
        labels = {a: self.label("case") for a in range(len(arms)) if a != inline}
        self.emit(depth, f"switch ((int){self.expr(value)})")
        self.emit(depth, "{")
        for k in range(n):
            self.emit(depth, f"case {k}:")
            if arm_of[k] != arm_of[k + 1]:
                self.emit(depth + 1, f"goto {labels[arm_of[k]]};")
        self.emit(depth, f"case {n}:")
        self.block(arms[inline][1], depth + 1)
        self.emit(depth, "}")
        if self.b.data and not self.data_placed:
            words = [self.binds.c_name(f) for f in self.b.data] + self.unit.jump_words()
            self.emit(depth, f"PLACE({', '.join(words)});")
            self.data_placed = True
        first, *apart = [a for a in range(len(arms)) if a != inline]
        after = self.label("next")
        self.emit(depth - 1, f"{labels[first]}:")
        self.block(arms[first][1], depth)
        if any(not self.ends_in_jump(arms[a][1]) for a in apart):
            self.emit(depth - 1, f"{after}:")
        main, self.out = self.out, []
        for a in apart:
            self.emit(0, f"{labels[a]}:")
            self.block(self.jumping_to(arms[a][1], ("goto", after, s[-1])), 1)
        self.tail += self.out
        self.out = main

    def ends_in_exit(self, stmts: list) -> bool:
        """The statements end in a jump, or a break out of the loop."""
        return bool(stmts) and (stmts[-1][0] == "break" or self.ends_in_jump(stmts))

    def jumping_to(self, stmts: list, jump: tuple) -> list:
        """stmts, then the jump: into each arm of a last if/else."""
        if self.ends_in_jump(stmts):
            return stmts
        last = stmts[-1] if stmts else None
        if last and last[0] == "if" and last[2]:
            return stmts[:-1] + [("if", [(c, self.jumping_to(b, jump)) for c, b in last[1]],
                                  self.jumping_to(last[2], jump), last[3])]
        return stmts + [jump]

    @staticmethod
    def exits_last(body: list) -> bool:
        """The loop's last statement is `if c: break`."""
        end = body[-1] if body else None
        return bool(end) and end[0] == "if" and len(end[1]) == 1 and not end[2] \
            and [x[0] for x in end[1][0][1]] == ["break"] \
            and not any(x[0] == "continue" for x in walk(body))

    def bottom_loop(self, s, depth: int, last: bool):
        """A loop whose last statement is `if c: break` is laid out with the
        test at the bottom, jumping back to the top while the exit is not
        taken. A break before it jumps past the loop, as a rotated loop's
        does; a break of a loop that ends the routine is its return."""
        _, _, body, where = s
        head = self.label("loop")
        cond = body[-1][1][0][0]
        if cond[0] != "bin" or cond[1] not in NEGATED:
            raise BindError(f"{where}: cannot negate {cond!r}")
        stay = ("bin", NEGATED[cond[1]], cond[2], cond[3])
        after = self.label("after") if breaks(body[:-1]) and not last else None
        self.loops.append((after, head))
        self.block([("label", head, where), *body[:-1], ("if", [(stay, [("goto", head, where)])], [], where)],
                   depth)
        self.loops.pop()
        if after:
            self.emit(depth - 1, f"{after}: ;")

    def display(self, s, nxt, depth: int) -> int:
        """A point to plot: x in AC, y in IO, as the display instruction
        takes them. A stream the binding shows with hlt, then a wait: the
        halt, which shows AC and IO on the console lights and waits."""
        _, stream, args, where = s
        how = self.binds.streams.get(stream)
        names = list(self.unit.prog.records[stream].fields)
        if how == "dpy" and args[2][0] == "num":
            x_text, y_text = self.registers(stream, names[:2], args[:2], depth)
            if self.b.pulse and not self.b.code:
                # each point asks for a completion pulse, and waits for the one before
                if args[2][1] != 0:
                    raise BindError(f"{where}: a point that asks for a pulse is plotted at intensity 0")
                if self.pulsed:
                    self.emit(depth, "ioh();")
                self.emit(depth, f"dpy_nowait({x_text}, {y_text});")
                self.pulsed = True
                return 1
            if nxt is not None and nxt[0] == "call" and self.binds.bound[nxt[1]].pulse:
                # the code that runs next waits for a completion pulse: ask for one
                if args[2][1] != 0:
                    raise BindError(f"{where}: a point that asks for a pulse is plotted at intensity 0")
                self.emit(depth, f"dpy_nowait({x_text}, {y_text});")
                return 1
            self.emit(depth, f"dpy({x_text}, {y_text}, {args[2][1]});")
            return 1
        if how == "hlt" and nxt is not None and nxt[0] == "wait":
            ac, io = self.registers(stream, names, args, depth)
            self.emit(depth, f"halt({ac}, {io});")
            return 2
        raise BindError(f"{where}: the binding shows no stream {stream} here")

    def registers(self, stream: str, names: list[str], args: list, depth: int) -> tuple[str, str]:
        """The two values in AC and IO. Two zeros are cleared by one
        instruction (cla cli); a pool word goes straight into AC."""
        x_text, y_text = self.expr(args[0]), self.expr(args[1])
        if args[0] == args[1] == ("num", 0):
            self.declare_top(f"word {stream}_{names[0]};")
            self.declare_top(f"register word {stream}_{names[1]};")
            self.emit(depth, f"{stream}_{names[0]} = 0, {stream}_{names[1]} = 0;")
            return f"{stream}_{names[0]}", f"{stream}_{names[1]}"
        if self.binds.streams.get(stream) == "dpy" and dotted_of(args[0]) in self.binds.pool:
            pass
        elif not self.ac_resident(x_text):
            self.declare_top(f"word {stream}_{names[0]};")
            self.emit(depth, f"{stream}_{names[0]} = {x_text};")
            x_text = f"{stream}_{names[0]}"
        if y_text.startswith("*home(") and self.base(y_text[6:-1]) in self.b.homes:
            self.unit.home_kinds[y_text[6:-1]] = "I_LIO"     # its home reads into IO
        if y_text not in self.io_resident():
            self.declare_top(f"register word {stream}_{names[1]};")
            self.emit(depth, f"{stream}_{names[1]} = {y_text};")
            y_text = f"{stream}_{names[1]}"
        return x_text, y_text

    def shift_word(self, count: str) -> str:
        """The shift instruction that holds a field's count, as xct runs it."""
        name = self.binds.c_name(count)
        return f"*home({name})" if self.binds.homes.get(count) == "table" else name

    def home(self, dotted: str, e, depth: int) -> int:
        """A set of a field held in a shift instruction. One held as a
        pointer into its table steps to the next entry, or starts at the
        first; one built at run time is the shift by as many places as the
        mask has bits."""
        name = self.binds.c_name(dotted)
        if dotted in self.binds.held:
            if e[0] == "call" and e[1] == "popcount":
                # built from a mask: the code with as many places as it has bits
                self.emit(depth, f"{name} = {self.unit.code_word(dotted, f'POPCOUNT({self.expr(e[2][0])})')};")
            elif held_field(e) and self.unit.copy_root(held_field(e)) == self.unit.copy_root(dotted):
                # a copy of another word that holds the same shift
                self.emit(depth, f"{name} = {self.expr(e)};")
            else:
                raise BindError(f"{self.b.name}: {dotted} is held as the code of its use: set it to "
                                f"popcount(w & m), or to a field that holds a shift of its kind")
            return 1
        table, v, known = self.unit.shift_table(dotted), e[1], self.known.get(dotted)
        if known is not None and table.index(known) + 1 < len(table) and table[table.index(known) + 1] == v:
            self.emit(depth, f"++{name};")
        elif v == table[0]:
            self.emit(depth, f"{name} = {name}_shifts;")
        else:
            raise BindError(f"{self.b.name}: {dotted} steps through its table in order")
        self.known[dotted] = v
        return 1

    def value(self, dotted: str, e) -> str:
        """e as the value of a field: a place by number in the collection a
        field holds a place in is that place's address."""
        if dotted in self.binds.into and e[0] == "num":
            return self.unit.address(self.binds.into[dotted], e[1])
        return self.expr(e)

    def word_of(self, e, into_pointer: bool = False) -> str:
        """e as a word: an address held as a pointer is cast to one."""
        text = self.expr(e)
        if dotted_of(e) in self.binds.pointers and not into_pointer:
            return f"(word){text}"
        return text

    def flag(self, held: str, e, depth: int) -> int:
        """A field or a local held in a program flag: the member spelled 1 sets it."""
        how = self.flag_word(e, held)
        n = self.b.flags[held] if held in self.b.flags else self.binds.flags[held]
        self.emit(depth, f"{'stf' if how else 'clf'}({n});")
        return 1

    def assign(self, s, nxt, last: bool, depth: int) -> int:
        _, target, e, where = s
        dotted = dotted_of(target)
        if target[0] == "index":
            held = dotted_of(target[1])
            value = self.value(held, e) if held in self.binds.into and e[0] == "num" else self.word_of(e)
            self.emit(depth, f"{self.cursor(target)} = {value};")
            return 1
        if dotted in self.binds.flags:
            return self.flag(dotted, e, depth)
        if dotted and self.binds.held_place(dotted):
            # the jump to the place: only its address changes (dap)
            self.emit(depth, f"{self.place(dotted)}.addr = {self.expr(e)};")
            return 1
        if self.binds.coded(dotted):
            return self.home(dotted, e, depth)
        if dotted and self.b.skips and dotted == self.b.skips[0]:
            if e[0] != "member":
                raise BindError(f"{where}: {dotted} takes a member")
            if e[2] == self.b.skips[1]:
                self.emit(depth, "skip_return();")
            return 1
        if e[0] == "call" and e[1] in IO_ROTATE and e[2][0] == target and self.expr(target) in self.io_resident():
            # a rotate of IO in place
            moved = self.expr(target)
            self.emit(depth, f"{moved} = {IO_ROTATE[e[1]]}({moved}, {self.expr(e[2][1])});")
            return 1
        if e[0] == "call" and e[1] in IO_ROTATE and self.expr(src := e[2][0]) in self.io_resident() \
                and not self.read_later(dotted_of(src) or src[1]):
            # pdp1cc rotates only AC: rotate IO in place, then move it
            moved = self.expr(src)
            self.emit(depth, f"{moved} = {IO_ROTATE[e[1]]}({moved}, {self.expr(e[2][1])});")
            e = src
        value = self.value(dotted, e) if dotted in self.binds.into \
            else self.word_of(e, into_pointer=dotted in self.binds.pointers)
        if dotted and self.binds.in_register(dotted, self.unit.path) and dotted not in self.alias \
                and re.fullmatch(r"\w+\.(hi|lo)", value):
            self.alias[dotted] = value          # the half of the pair the register already holds
            return 1
        device = self.binds.devices.get(dotted_of(e) or "")
        into_io = dotted in self.binds.io_fields or (target[0] == "name" and target[1] in self.b.io)
        if device and into_io and not device.get("or_into_io"):
            # the device reads into AC: move it to IO
            if self.unit.spec.get("moves") != "swap":
                raise BindError(f"{self.b.name}: the binding moves no value from AC to IO")
            value = f"SWAP({value})"
        if dotted and self.own_result_local(dotted) and (last or (nxt is not None and nxt[0] == "return")) \
                and not (device and device.get("or_into_io")):
            self.emit(depth, self.return_text(value))
            return 2 if nxt is not None else 1
        name = self.place(dotted) if dotted else self.alias.get(target[1], target[1])
        if dotted and name == leaf(dotted) and name not in self.own.values() and not self.declared(name):
            kind = "register word" if dotted in self.binds.io_fields else "word"
            kind = "word *" if dotted in self.binds.pointers else kind + " "
            if self.has_table:
                # the arms of a jump table lie apart and share their locals: declared at the top
                self.declare_top(f"{kind}{name};")
                self.scopes[0].add(name)
                self.emit(depth, f"{name} = {value};")
                return 1
            if device and device.get("or_into_io"):
                # the device ors into IO: clear it first
                self.emit(depth, f"{kind}{name} = 0;")
                self.emit(depth, f"{name} = {value};")
            else:
                self.emit(depth, f"{kind}{name} = {value};")
            self.scopes[-1].add(name)
            return 1
        self.emit(depth, f"{name} = {value};")
        return 1

    def pair(self, s, depth: int):
        """A shift of the AC:IO pair works in place: its result goes back to
        the halves it came from. A new name for a half is that half."""
        op, (_, targets), e, where = s[0], s[1], s[2], s[-1]
        if e[0] != "call" or e[1] not in PAIR_OPS:
            raise BindError(f"{where}: a pair is set only by a pair operator")
        halves = [self.expr(a) for a in e[2][:2]]
        if self.binds.coded(count := dotted_of(e[2][2])):
            self.emit(depth, f"pair = xct({self.shift_word(count)}, {', '.join(halves)});")
        else:
            self.emit(depth, f"{e[1]}({', '.join(halves + [self.expr(e[2][2])])});")
        for t, half in zip(targets, halves):
            if op == "let" and t[0] == "name":
                self.alias[t[1]] = half
            elif self.expr(t) != half:
                raise BindError(f"{where}: a pair shift's result goes back where it came from")

    def call(self, s, last: bool, depth: int):
        _, name, args, where = s
        callee = self.binds.bound[name]
        jump = self.unit.jumps(callee, s, self.stmts)
        target = callee.block if jump else callee.name
        if missing := [f for f, _ in callee.params(block=jump) if f not in args]:
            raise BindError(f"{where}: {name} takes {missing} as parameters: the RUNS sets them just before the run")
        text = f"{target}({', '.join(self.value(f, args[f]) for f, _ in callee.params(block=jump))})"
        if callee.convention == "BLOCK":
            # A run of a block is a jump to it; the firing goes on there.
            if name in self.binds.carried:
                text = f"(*home({name}))()"
            self.emit(depth, f"return {text};")
            return
        if last and callee.result == self.b.result and bool(callee.skips) == bool(self.b.skips):
            self.emit(depth, f"return {text};")
            return
        if not jump and len(callee.result) < 2 and not callee.skips:
            # The result is in AC when the call returns: the next statement
            # takes it from there (block), or the call stands alone. A result
            # in the register the routine also takes it in stays there.
            if callee.result and callee.result[0] in args and self.binds.in_register(callee.result[0], self.unit.path) \
                    and self.read_later(callee.result[0]):
                self.emit(depth, f"{self.place(callee.result[0])} = {text};")
            elif callee.result:
                self.pending = (callee.result[0], text, self.nested)
            else:
                self.emit(depth, f"{text};")
            if callee.pulse and not callee.code:
                self.emit(depth, "ioh();")      # wait for the pulse its last point asked for
            return
        if jump or len(callee.result) != 2:
            raise BindError(f"{where}: run {name} here is not a call the binding can lay out")
        local = self.results.get(name)
        stale = {k for k, v in self.alias.items() if local and v.startswith(local + ".")}
        for k in stale:
            del self.alias[k]
        if local is None:
            local = self.results[name] = f"{name}_result"
            self.emit(depth, f"{'shift_pair' if callee.returns_shift else 'dword'} {local} = {text};")
        else:
            self.emit(depth, f"{local} = {text};")
        self.alias[callee.result[0]] = f"{local}.hi"
        self.alias[callee.result[1]] = f"{local}.lo"

    def guards(self, stmts: list) -> list:
        """An if with no else that ends the routine, or ends the arm of such
        an if, is a guard: its test, negated, leaves the routine, and its arm
        follows in line. The first return after the Processor the binding
        names (exit_after) is the routine's exit; the returns after it jump
        there (return_text)."""
        last = stmts[-1] if stmts else None
        if not last or last[0] != "if" or len(last[1]) != 1 or last[2] or table_cases(last):
            return stmts
        (c, arm), where = last[1][0], last[3]
        if c[0] != "bin" or c[1] not in NEGATED:
            raise BindError(f"{where}: cannot negate {c!r}")
        leave = ("if", [(("bin", NEGATED[c[1]], c[2], c[3]), [("return", where)])], [], where)
        return stmts[:-1] + [leave] + self.guards(arm)

    def apart_loop(self, s, nxt, depth: int) -> int:
        """A loop laid out with its arms apart (arms = "apart"): the body in
        line from a label, a jump back to it, then the first arm of each of
        its ifs with an else, in the order they come (apart_if), each
        jumping back. The loop's breaks are one jump out, laid out where the
        first break stands; the others jump to it. Data words laid out at
        the copy's end follow, then the code after the loop."""
        _, _, body, where = s
        top, done, after = self.label("look"), self.label("done"), self.label("after")
        first = [True]

        def share(stmts):
            out = []
            for x in stmts:
                if x[0] == "break":
                    out += [("label", done, x[-1]), ("goto", after, x[-1])] if first[0] else [("goto", done, x[-1])]
                    first[0] = False
                elif x[0] == "if":
                    out.append(("if", [(c, share(b)) for c, b in x[1]], share(x[2]), x[3]))
                else:
                    out.append(x)
            return out
        body = share(body)
        self.emit(depth - 1, f"{top}:")
        self.apart.append({"top": top, "body": id(body), "arms": []})
        self.block(body, depth)
        self.emit(depth, f"goto {top};")
        loop = self.apart.pop()
        for label, arm, join in loop["arms"]:
            self.emit(depth - 1, f"{label}:")
            self.block(self.rejoining(arm, join), depth)
        used = 1
        if nxt is not None and nxt[0] == "data_here":
            self.emit(depth, f"PLACE({', '.join(nxt[1])});")
            used = 2
        self.emit(depth - 1, f"{after}: ;")
        return used

    def apart_if(self, s, stmts: list, k: int, depth: int):
        """An if with an else, in a loop laid out apart: its test jumps to
        its first arm, laid out after the loop; the rest of the chain lies
        in line, and the arm jumps back to the code after the if, or to the
        loop's top when the if ends the loop's body."""
        _, arms, other, where = s
        loop = self.apart[-1]
        (c, arm), rest = arms[0], arms[1:]
        label = self.label("apart")
        ends_body = k == len(stmts) - 1 and id(stmts) == loop["body"]
        join = loop["top"] if ends_body else self.label("join")
        self.emit(depth, f"if ({self.cond(c)})")
        self.emit(depth + 1, f"goto {label};")
        self.block([("if", rest, other, where)] if rest else other, depth)
        if not ends_body:
            self.emit(depth - 1, f"{join}:")
        loop["arms"].append((label, arm, join))

    def rejoining(self, stmts: list, join: str) -> list:
        """An arm laid out apart, then its jump back. An if with no else
        that ends it jumps back when its test fails, and its arm then jumps
        back too."""
        back = ("goto", join, stmts[-1][-1] if stmts else "")
        if self.ends_in_jump(stmts):
            return stmts
        last = stmts[-1] if stmts else None
        if last and last[0] == "if" and len(last[1]) == 1 and not last[2] and not self.ends_in_jump(last[1][0][1]):
            (c, arm), where = last[1][0], last[3]
            if c[0] != "bin" or c[1] not in NEGATED:
                raise BindError(f"{where}: cannot negate {c!r}")
            stay = ("if", [(("bin", NEGATED[c[1]], c[2], c[3]), [back])], [], where)
            return stmts[:-1] + [stay] + arm + [back]
        return stmts + [back]

    def loop(self, s, depth: int):
        """The exit-first layout. The body runs up to its first exit, which
        falls through into the code after the loop; the rest of the body is
        laid out after the function's last return, and jumps back to the
        top. When the statement before the loop is `if c: X` and the body
        ends with X, the top is that X: the loop is entered at X or past it."""
        _, _, body, where = s
        first = next((n for n, x in enumerate(body) if x[0] == "if" and len(x[1]) == 1 and not x[2]
                      and x[1][0][1] and x[1][0][1][-1][0] == "break"), None)
        if first is None:
            raise BindError(f"{where}: an exit-first loop needs an `if c: ... break`")
        rest = body[first + 1:]
        if self.merged_head and self.merged_head[0] is s:
            head = self.merged_head[1]
            rest = rest[:-1]
        else:
            head = self.label("loop")
            self.emit(depth, f"{head}:")
        self.merged_head = None
        after, past = self.label("after"), self.label("rest")
        self.block(body[:first], depth)
        cond, exit_body = body[first][1][0]
        self.emit(depth, f"if ({self.cond(cond, negate=True)})")
        self.emit(depth + 1, f"goto {past};")
        self.loops.append((after, head))
        main, self.out = self.out, []
        self.emit(0, f"{past}:")
        self.block(rest, 1)
        self.emit(1, f"goto {head};")
        self.tail += self.out
        self.out = main
        self.block(exit_body[:-1], depth)
        self.loops.pop()
        self.emit(depth, f"{after}:")


class Taint(Exception):
    """A choice, or something the routine cannot follow bit by bit, depends
    on the value."""


def ignores(routine: runs.Routine, name: str, where: str) -> bool:
    """Whether a Processor's effects depend on no bit of the value its
    statement at `where` reads as `name`. Each word is followed bit by bit:
    a shift, a rotate or a mask moves or drops bits, the pair shifts as the
    machine does them; add, subtract and the rest mix every bit. True when
    no bit of that value reaches a field the Processor writes, a point it
    plots, a value it returns or a guard it tests."""
    clean, dirty = [False] * 18, [True] * 18

    def any_of(*vs) -> list[bool]:
        return [any(b for v in vs for b in v)] * 18

    def shifted(v: list, op: str, n: int) -> list:
        for _ in range(n):
            if op == ">>":
                v = v[1:] + [v[17]]
            elif op == "<<":
                v = [v[17]] + v[:16] + [v[17]]
            elif op == "ral":
                v = [v[17]] + v[:17]
            elif op == "rar":
                v = v[1:] + [v[0]]
        return v

    def paired(op: str, h: list, lo: list, n: int) -> tuple[list, list]:
        for _ in range(n):
            if op == "rcl":
                h, lo = [lo[17]] + h[:17], [h[17]] + lo[:17]
            elif op == "rcr":
                h, lo = h[1:] + [lo[0]], lo[1:] + [h[0]]
            elif op == "scl":
                h, lo = [lo[17]] + h[:16] + [h[17]], [h[17]] + lo[:17]
            elif op == "scr":
                h, lo = h[1:] + [h[17]], lo[1:] + [h[0]]
        return h, lo

    def number(e) -> int | None:
        return e[1] if e[0] == "num" else None

    def value(e, env: dict):
        op = e[0]
        if op in ("num", "member", "bool"):
            return clean
        if op == "name":
            return dirty if e[1] == name and env["@"] == where else env.get(e[1], clean)
        if op == "field":
            d = dotted_of(e)
            return dirty if d == name and env["@"] == where else env.get(d, clean)
        if op == "index":
            if any(value(e[2], env)):
                raise Taint()
            return value(e[1], env)
        if op == "neg":
            return value(e[1], env)
        if op == "call" and e[1] in ("ral", "rar") and number(e[2][1]) is not None:
            return shifted(value(e[2][0], env), e[1], number(e[2][1]))
        if op == "call" and e[1] in PAIR_OPS and len(e[2]) == 3 and e[1] not in ("mus", "dis") \
                and number(e[2][2]) is not None:
            return paired(e[1], value(e[2][0], env), value(e[2][1], env), number(e[2][2]))
        if op == "call":
            v = any_of(*(value(a, env) for a in e[2]))
            return (v, v) if e[1] in PAIR_OPS else v
        if op == "tuple":
            return tuple(value(x, env) for x in e[1])
        if op == "bin":
            _, o, a, b = e
            if o in ("<<", ">>") and number(b) is not None:
                return shifted(value(a, env), o, number(b))
            if o in ("&", "|") and (number(b) is not None or number(a) is not None):
                mask, v = (number(b), value(a, env)) if number(b) is not None else (number(a), value(b, env))
                bits = runs.word_of(mask).v
                keep = (lambda i: bits >> i & 1) if o == "&" else (lambda i: not bits >> i & 1)
                return [v[i] and bool(keep(i)) for i in range(18)]
            if o == "^":
                return [x or y for x, y in zip(value(a, env), value(b, env))]
            return any_of(value(a, env), value(b, env))
        raise Taint()

    def assign(target, v, env: dict):
        if target[0] == "tuple":
            for t, x in zip(target[1], v):
                assign(t, x, env)
        elif target[0] == "name":
            env[target[1]] = v
        elif target[0] == "index":
            if any(value(target[2], env)) or any(v):
                raise Taint()
        else:
            env[dotted_of(target)] = v          # its last value is the Processor's effect

    def joined(*envs: dict) -> dict:
        """Either path's words: a bit is dirty when it is on either."""
        out = {"@": None}
        for k in set().union(*envs) - {"@"}:
            vs = [e.get(k, clean) for e in envs]
            out[k] = [any(bits) for bits in zip(*vs)]
        return out

    def block(stmts: list, env: dict) -> dict:
        for s in stmts:
            op = s[0]
            env = {**env, "@": s[-1]}
            if op in ("let", "set"):
                assign(s[1], value(s[2], env), env)
            elif op == "if":
                outs = []
                for c, body in s[1]:
                    if any(value(c, env)):
                        raise Taint()
                    outs.append(block(body, dict(env)))
                outs.append(block(s[2], dict(env)))
                env = joined(*outs)
            elif op in ("loop", "for"):
                if any(any(value(b, env)) for b in (s[1:2] if op == "loop" else s[2:4])):
                    raise Taint()               # how many passes is a choice
                for _ in range(64):             # the words after any number of passes: until it settles
                    exits.append([])
                    end = block(s[-2], dict(env))
                    after = joined(env, end, *exits.pop())
                    if after == {**env, "@": None}:
                        break
                    env = after
                else:
                    raise Taint()
            elif op == "emit":
                if any(any(value(a, env)) for a in s[2]):
                    raise Taint()
            elif op == "return":
                if effects(env):
                    raise Taint()
            elif op in ("break", "continue"):
                exits[-1].append(dict(env))
            else:
                raise Taint()
        return env

    def effects(env: dict) -> bool:
        return any(any(v) for k, v in env.items() if "." in k)
    exits: list[list] = []
    try:
        env = block(routine.body, {"@": None})
    except Taint:
        return False
    return not effects(env)


class UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        while self.parent.setdefault(x, x) != x:
            x = self.parent[x]
        return x

    def union(self, names):
        names = list(names)
        for x in names[1:]:
            self.parent[self.find(x)] = self.find(names[0])

    def groups(self) -> dict[str, set[str]]:
        """root -> its names, for groups of two or more."""
        out: dict[str, set[str]] = {}
        for x in self.parent:
            out.setdefault(self.find(x), set()).add(x)
        return {root: names for root, names in out.items() if len(names) > 1}


PASSED = "@passed"


class SharedWords:
    """Which RUNS names a shared word holds, through every bound routine.
    Names share a word when the binding puts them there (an entry word and
    its cells, a [share]) or when runsc compiles them to one C name (a local
    kept in the register a field arrived in, the halves of a pair, a call's
    result). A word holds the value of the last name written to it, and of
    the names copied from that one since. A read of any other name is a
    BindError: the RUNS text would read a value the machine no longer has.

    The binding's words carry from a routine into the routines it runs: a
    routine starts with what every run of it leaves there. A top Network,
    which the host fires, starts with nothing known, so a [share] field is
    set before it is read in every firing."""

    def __init__(self, binds: "Bindings", compiled: list[tuple["Function", list]]):
        self.binds = binds
        self.prog = binds.prog
        self.compiled = compiled
        self.words = UnionFind()
        for b in binds.bound.values():
            if b.entry and b.cells:
                self.words.union([b.entry, *b.cells])
        for f, other in binds.shared.items():
            self.words.union([f, other])
        self.shared = self.words.groups()       # root -> the fields that share its word
        self.processor_at = {s[-1]: r for r in self.prog.routines.values() if r.kind == "processor"
                             for s in walk(r.body)}

    def check(self):
        fired = set().union(set(), *(runs.runs_of(r.body) for r in self.prog.routines.values()))
        entry: dict[str, dict] = {}
        todo = []
        for fn, _ in self.compiled:
            if fn.b.name not in fired and fn.b.name not in entry:
                entry[fn.b.name] = {}
                todo.append(fn.b.name)
        for _ in range(10000):
            if not todo:
                break
            name = todo.pop()
            for fn, stmts in self.compiled:
                if fn.b.name != name:
                    continue
                for callee, state in Occupancy(self, fn, entry[name]).run(stmts):
                    old = entry.get(callee)
                    new = state if old is None else {g: old.get(g, frozenset()) & state.get(g, frozenset())
                                                      for g in [*self.shared, PASSED]}
                    if new != old:
                        entry[callee] = new
                        todo.append(callee)
        for fn, stmts in self.compiled:
            if fn.b.name not in entry:          # entered only from outside the RUNS (none today)
                Occupancy(self, fn, {}).run(stmts)


class Occupancy:
    """SharedWords through one bound routine's statements, as the RUNS runs
    them (each branch with its own copy of a shared tail)."""

    def __init__(self, words: SharedWords, fn: Function, entry: dict):
        self.words = words
        self.fn = fn
        self.prog = fn.unit.prog
        self.names = UnionFind()
        for names in words.shared.values():
            self.names.union(sorted(names))
        for names in fn.storage.values():
            self.names.union(sorted(names))
        self.members = self.names.groups()
        self.group = {x: root for root, names in self.members.items() for x in names}
        self.entry = entry
        self.calls: list[tuple[str, dict]] = []    # (routine run, the binding's words as it starts)
        self.loops: list[tuple[list, list]] = []   # (states at its breaks, states at its continues)
        self.labels: dict[str, list] = {}
        self.seen_labels: set[str] = set()

    def run(self, stmts: list) -> list[tuple[str, dict]]:
        b = self.fn.b
        state: dict[str, frozenset] = {}
        for root, holders in self.entry.items():
            if root != PASSED:
                g = self.group[next(iter(self.words.shared[root]))]
                state[g] = state.get(g, frozenset()) | holders
        passed = self.entry.get(PASSED, frozenset())
        for f in [b.entry, *(f for f in [b.ac_param, b.io_param, b.byname, b.inline, *self.fn.own] if f in passed)]:
            if f in self.group:
                state[self.group[f]] = state.get(self.group[f], frozenset()) | {f}
        end = self.block(stmts, state)
        if end is not None:
            self.leave(end, b.name)
        return self.calls

    def leave(self, state: dict, where: str):
        """The routine returns its result fields: each word must hold its own.
        A word the binding gives fields (an entry word and its cells, a
        [share], a register a Record's field lives in) must not be left
        holding only the routine's locals: the RUNS field would keep a value
        the machine no longer has."""
        binds = self.fn.binds
        for g, names in self.members.items():
            lasting = sorted(f for f in names if f in binds.cell_of or f in binds.shared
                             or f in binds.shared.values() or "." in f and f.split(".")[0] in binds.registers)
            holders = state.get(g, frozenset())
            if lasting and holders and not any("." in x for x in holders):
                raise BindError(f"{where}: {self.fn.b.name} leaves the word of {lasting[0]} holding its local "
                                f"{sorted(holders)[0]}")
        for f in self.fn.b.result:
            g = self.group.get(f)
            if g is not None and f not in state.get(g, frozenset()):
                raise BindError(f"{where}: {self.fn.b.name} returns {f}, but its word holds "
                                f"{sorted(state.get(g, frozenset())) or 'no name set on every path'}")

    def export(self, state: dict, passed=frozenset()) -> dict:
        """The binding's shared words, as a routine run here starts, and the
        parameters the run hands it (PASSED): a register a routine reads is
        its parameter only where every run of it sets it just before."""
        return {root: state.get(self.group[next(iter(names))], frozenset()) & names
                for root, names in self.words.shared.items()} | {PASSED: frozenset(passed)}

    def kill(self, state: dict, routines, keep_own=False) -> dict:
        """What the routines may write no longer holds what it held. Code
        the game runs (`jump`) writes a word only through the name its
        operand gives, a field of a Record the jump declares: a word that
        held that field still holds it, whether the code wrote it or not."""
        written = set().union(set(), *(self.prog.routines[p].writes for r in routines if r in self.prog.routines
                                       for p in runs.fires(self.prog, r, set())
                                       if self.prog.routines[p].kind == "processor"))
        out = {}
        for g, names in state.items():
            own = {x for x in self.members[g] if "." in x and x.split(".")[0] in written}
            if not own:
                out[g] = names
            elif keep_own and len(own) == 1 and own <= names:
                out[g] = frozenset(own)
        return out

    def read(self, name: str, state: dict, where: str):
        g = self.group.get(name)
        processor = self.words.processor_at.get(where)
        if g is not None and name not in state.get(g, frozenset()) \
                and not (processor and ignores(processor, name, where)):
            holds = sorted(state.get(g, frozenset())) or "no name set before it on every path"
            raise BindError(f"{where}: {name} is read where its word, which the binding shares with "
                            f"{sorted(self.members[g] - {name})}, holds {holds}")

    def reads(self, e, state: dict, where: str):
        if not isinstance(e, tuple) or not e:
            return
        op = e[0]
        if op == "name":
            self.read(e[1], state, where)
        elif op == "field":
            if (d := dotted_of(e)) is not None:
                self.read(d, state, where)
        elif op == "index":
            self.reads(e[2], state, where)
        elif op in ("call", "tuple"):
            for x in (e[2] if op == "call" else e[1]):
                self.reads(x, state, where)
        elif op in ("bin", "neg", "not"):
            for x in e[1:]:
                self.reads(x, state, where)

    def write(self, target, state: dict, copied=None):
        name = target[1] if target[0] == "name" else dotted_of(target)
        g = self.group.get(name)
        if g is None:
            return
        if copied is not None and self.group.get(copied) == g and copied in state.get(g, frozenset()):
            state[g] = state[g] | {name}            # the same value, kept where it was
        else:
            state[g] = frozenset({name})

    @staticmethod
    def join(states: list) -> dict | None:
        live = [s for s in states if s is not None]
        if not live:
            return None
        keys = set().union(*live)
        return {g: frozenset.intersection(*(s.get(g, frozenset()) for s in live)) for g in keys}

    def block(self, stmts: list, state: dict | None) -> dict | None:
        for s in stmts:
            if state is None and s[0] != "label":
                continue                            # reached only by a label
            state = self.stmt(s, state)
        return state

    def loop_body(self, body: list, state: dict) -> list:
        """The states at a loop's exits, its top joined over every pass."""
        top = dict(state)
        for _ in range(20):
            self.loops.append(([], []))
            end = self.block(body, dict(top))
            breaks, continues = self.loops.pop()
            new = self.join([state, end, *continues])
            if new == top:
                return breaks + [end]
            top = new
        raise BindError(f"{self.fn.b.name}: the shared words' contents do not settle in a loop")

    def stmt(self, s, state: dict | None) -> dict | None:
        op, where = s[0], (s[-1] if isinstance(s[-1], str) else "")
        if op == "label":
            self.seen_labels.add(s[1])
            return self.join([state, *self.labels.pop(s[1], [])])
        if op == "goto":
            if s[1] in self.seen_labels:
                raise BindError(f"{where}: a jump back to {s[1]}: runsc follows shared words forward only")
            self.labels.setdefault(s[1], []).append(dict(state))
            return None
        state = dict(state)
        if op in ("let", "set"):
            self.reads(s[2], state, where)
            targets = s[1][1] if s[1][0] == "tuple" else [s[1]]
            for t in targets:
                if t[0] == "index":
                    self.reads(t[2], state, where)
            if s[1][0] == "tuple":
                for t in targets:
                    if t[0] != "index":
                        self.write(t, state)
            elif s[1][0] != "index":
                source = s[2][1] if s[2][0] == "name" else dotted_of(s[2]) if s[2][0] == "field" else None
                self.write(s[1], state, copied=source)
            return state
        if op == "if":
            outs = []
            for c, body in s[1]:
                self.reads(c, state, where)
                outs.append(self.block(body, dict(state)))
            outs.append(self.block(s[2], dict(state)))
            return self.join(outs)
        if op == "loop":
            return self.join(self.loop_body(s[2], state)[:-1])     # a loop leaves by its breaks
        if op in ("for", "slots"):
            self.reads(s[2], state, where)
            self.reads(s[3], state, where)
            return self.join(self.loop_body(s[4], state) + [state])
        if op in ("break", "continue"):
            if self.loops:
                self.loops[-1][0 if op == "break" else 1].append(state)
            return None
        if op in ("return", "stop", "unreachable"):
            if op == "return":
                self.leave(state, where)
            return None
        if op == "emit":
            for a in s[2]:
                self.reads(a, state, where)
            return state
        if op == "call":
            callee = self.fn.binds.bound[s[1]]
            for e in s[2].values():
                self.reads(e, state, where)
            self.calls.append((s[1], self.export(state, s[2])))
            state = self.kill(state, [s[1]], keep_own=callee.code)
            if callee.code and callee.back:
                self.calls.append((callee.back, self.export(state)))
            for f in callee.result:
                self.write(as_field(f), state)
            return state
        if op == "dispatch":
            self.reads(s[1], state, where)
            self.calls += [(t, self.export(state)) for t in s[3]]
            return self.kill(state, s[3])
        if op == "shared":
            return self.block(s[2], state)
        if op in ("cursors", "clear", "args_done", "exit_next", "data_here", "wait", "load_io"):
            return state
        raise BindError(f"{where}: runsc cannot follow shared words through {op}")


def write_tree(prog: runs.Program, out: Path) -> Path:
    """lift.toml under out, each unit compiled from RUNS: out's
    lift/ holds the generated C and nothing else. Returns the toml."""
    lift = tomllib.loads((PROGRAM / "lift.toml").read_text())
    paths = sorted(BINDINGS.glob("*.toml"))
    binds = Bindings(prog, paths)
    bound = {spec["replaces"]: p for p, spec in binds.specs.items()}

    generated = out / "lift"
    if generated.exists():
        for f in generated.iterdir():
            f.unlink()
    generated.mkdir(parents=True, exist_ok=True)
    units = []
    for u in lift["unit"]:
        if u["c"] not in bound:
            raise BindError(f"no binding replaces {u['c']}: every unit comes from RUNS")
        path, c, mark = bound.pop(u["c"]), out / u["c"], len(binds.compiled)
        unit = Unit(binds, path)
        c.write_text(unit.compile())
        if unit.run_fields:
            # what the members' words need comes from pdp1cc's words for them: compile again with it
            code = unit.run_code(c)
            del binds.compiled[mark:]
            c.write_text(Unit(binds, path, code).compile())
        units.append(f'[[unit]]\nc = "{u["c"]}"\nprefix = "{u["prefix"]}"\n')
    if bound:
        raise BindError(f"bindings replace no lift unit: {sorted(bound)}")
    SharedWords(binds, binds.compiled).check()
    toml = out / "lift.toml"
    head = "".join(f'{k} = "{ROOT / v if k in ("macro1", "macro1_src", "oracle_listing") else v}"\n'
                   for k, v in lift.items() if k != "unit")
    toml.write_text(head + "\n" + "\n".join(units))
    return toml


def build(prog: runs.Program, out: Path = OUT) -> int:
    """Compile and assemble; pdp1cc prints the hash and, on a mismatch, the
    first word that differs. 0 when the image is the original's. RUNS the
    evaluator rejects before anything runs is not compiled."""
    try:
        runs.check(prog)
    except runs.RunsError as e:
        raise BindError(f"the evaluator rejects the RUNS: {e}") from e
    toml = write_tree(prog, out)
    with contextlib.redirect_stdout(io.StringIO()) as said:
        code = program.build(toml)
    build.said = said.getvalue()
    return code


if __name__ == "__main__":
    code = build(runs.program(runs.source()))
    print(build.said, end="")
    sys.exit(code)
