"""A reference evaluator for the RUNS draft used by this port.

It reads .runs files (types, enums, records, streams, networks) and
.runs-prim files (processors), and runs a Network over Records.

The evaluator enforces the paradigm, not just the syntax. The topology is a
Petri net: Records are places, Processors are transitions.
- a processor reads only the Records it declares (reads or writes), and
  writes only the ones it declares under writes; it fires no other routine;
- a processor or network with Ports (in, out, inout) names no Record: each
  run wires every Port to one field, and the run fires a copy of the
  routine with each Port replaced by its field, one copy a wiring. A
  network's scratch (owns) is one field only it touches;
- a network writes nothing: it only fires processors and networks, chooses
  with guards that read Records, and loops with a bound and a guarded exit;
- nothing calls a routine from an expression. The only calls are the word's
  own operators (rcl, scr, popcount, ...), so every value that passes from
  one routine to another goes through a Record;
- a field with no initial value is unknown until the game sets it or the
  world gives it: reading it unknown is an error, and a top Network whose
  Processors read it declares its Record under reads:;
- `wait` hands the world the firing: the host shows what has left the game
  and may change what comes in, then the firing goes on;
- `jump` runs words of code a Record holds, by the original machine's rules
  for the instructions the machine description declares (`type insn`).

The word type is the PDP-1's 18-bit ones' complement word, with the
operations as the machine computes them."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MASK = 0o777777
SIGN = 0o400000


# ---------------------------------------------------------------- the word

@dataclass(frozen=True)
class W:
    v: int

    def __repr__(self) -> str:
        return f"W({self.v:06o})"


def word_of(n: int) -> W:
    if n > MASK or -n > MASK:
        raise RunsError(f"{n} does not fit a word")
    return W((~(-n)) & MASK if n < 0 else n)


def as_word(x) -> W:
    if isinstance(x, W):
        return x
    if isinstance(x, int) and not isinstance(x, bool):
        return word_of(x)
    raise RunsError(f"not a word: {x!r}")


def as_count(x) -> int:
    if isinstance(x, int) and not isinstance(x, bool):
        return x
    if isinstance(x, W) and not x.v & SIGN:
        return x.v
    raise RunsError(f"not a count: {x!r}")


def add(a: W, b: W) -> W:
    r = a.v + b.v
    if r > MASK:
        r = (r + 1) & MASK
    return W(0 if r == MASK else r)


def sub(a: W, b: W) -> W:
    r = (a.v ^ MASK) + b.v
    if r > MASK:
        r = (r + 1) & MASK
    return W(r ^ MASK)


def sal(a: W, n: int) -> W:
    v = a.v
    for _ in range(n):
        v = (v & SIGN) | ((v << 1) & (MASK >> 1)) | (1 if v & SIGN else 0)
    return W(v)


def sar(a: W, n: int) -> W:
    v = a.v
    for _ in range(n):
        v = (v >> 1) | (v & SIGN)
    return W(v)


def ral(a: W, n: int) -> W:
    v = a.v
    for _ in range(n):
        v = ((v << 1) | (v >> 17)) & MASK
    return W(v)


def rar(a: W, n: int) -> W:
    v = a.v
    for _ in range(n):
        v = ((v >> 1) | ((v & 1) << 17)) & MASK
    return W(v)


def rcl(h: W, l: W, n: int) -> tuple[W, W]:
    hv, lv = h.v, l.v
    for _ in range(n):
        c = (hv >> 17) & 1
        hv = ((hv << 1) | ((lv >> 17) & 1)) & MASK
        lv = ((lv << 1) | c) & MASK
    return W(hv), W(lv)


def rcr(h: W, l: W, n: int) -> tuple[W, W]:
    hv, lv = h.v, l.v
    for _ in range(n):
        c = lv & 1
        lv = ((lv >> 1) | ((hv & 1) << 17)) & MASK
        hv = ((hv >> 1) | (c << 17)) & MASK
    return W(hv), W(lv)


def scl(h: W, l: W, n: int) -> tuple[W, W]:
    hv, lv = h.v, l.v
    for _ in range(n):
        s = hv & SIGN
        hv = s | ((hv << 1) & (MASK >> 1)) | ((lv >> 17) & 1)
        lv = ((lv << 1) | (1 if s else 0)) & MASK
    return W(hv), W(lv)


def scr(h: W, l: W, n: int) -> tuple[W, W]:
    hv, lv = h.v, l.v
    for _ in range(n):
        lv = ((lv >> 1) | ((hv & 1) << 17)) & MASK
        hv = (hv & SIGN) | (hv >> 1)
    return W(hv), W(lv)


def mus(h: W, l: W, m: W) -> tuple[W, W]:
    ac = h.v
    if l.v & 1:
        ac += m.v
        if ac > MASK:
            ac = (ac + 1) & MASK
    return W(ac >> 1), W((l.v >> 1) | ((ac & 1) << 17))


def dis(h: W, l: W, m: W) -> tuple[W, W]:
    top = h.v >> 17
    ac = ((h.v << 1) | (l.v >> 17)) & MASK
    lv = ((l.v << 1) | (top ^ 1)) & MASK
    ac = ac + (m.v ^ MASK) if lv & 1 else ac + m.v + 1
    if ac > MASK:
        ac = (ac + 1) & MASK
    return W(0 if ac == MASK else ac), W(lv)


BUILTINS = {
    "ral": lambda a, n: ral(as_word(a), as_count(n)),
    "rar": lambda a, n: rar(as_word(a), as_count(n)),
    "rcl": lambda h, l, n: rcl(as_word(h), as_word(l), as_count(n)),
    "rcr": lambda h, l, n: rcr(as_word(h), as_word(l), as_count(n)),
    "scl": lambda h, l, n: scl(as_word(h), as_word(l), as_count(n)),
    "scr": lambda h, l, n: scr(as_word(h), as_word(l), as_count(n)),
    "mus": lambda h, l, m: mus(as_word(h), as_word(l), as_word(m)),
    "dis": lambda h, l, m: dis(as_word(h), as_word(l), as_word(m)),
    "popcount": lambda a: bin(as_word(a).v).count("1"),
}


# ------------------------------------------------------------ instructions

# The instructions of the original machine the game reaches, and the kind
# of operand each takes: a word of a Record (`place`), a word of code or a
# routine (`target`), a number, or none. The machine description declares
# which of them the game uses (`type insn`); their rules are in Machine.execute.
OPERANDS = {"lac": "place", "lio": "place", "dac": "place", "dio": "place", "add": "place",
            "sub": "place", "jmp": "target", "stf": "number", "clf": "number", "szf": "number",
            "rcl": "number", "cma": None, "ioh": None, "dpy": None}


@dataclass(frozen=True)
class Place:
    """A word of a Record, as an instruction names it."""
    record: str
    field: str
    slot: int | None = None


@dataclass(frozen=True)
class Insn:
    """A word of code: an instruction and its operand (a Place, a routine's
    name, a number, or None)."""
    op: str
    operand: object = None

    def __repr__(self) -> str:
        x = self.operand
        if isinstance(x, Place):
            x = f"{x.record}.{x.field}" + ("" if x.slot is None else f"[{x.slot:o}]")
        return self.op if x is None else f"{self.op}({x})"


# The instructions the program being loaded declares, for the parser.
declared_instructions: set[str] = set()


def instruction_call(name: str, args: list) -> bool:
    """name(args) builds an instruction: one operand, or none. `rcl` with
    three is the pair operator."""
    return name in declared_instructions and len(args) == (OPERANDS[name] is not None)


# ------------------------------------------------------------------ lexing

class RunsError(Exception):
    pass


TOKEN = re.compile(r"\s*(?:(\d+)|([A-Za-z_][A-Za-z0-9_]*)|(\.\.|->|==|!=|<=|>=|<<|>>|[-+&|^~<>=()\[\],:.]))")


def tokens(text: str, where: str) -> list[str]:
    out, pos = [], 0
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise RunsError(f"{where}: cannot read {text[pos:]!r}")
        out.append(next(g for g in m.groups() if g is not None))
        pos = m.end()
    return out


@dataclass
class Line:
    toks: list[str]
    where: str
    children: list["Line"] = field(default_factory=list)


def lines(path: Path) -> list[Line]:
    root = Line([], str(path))
    stack = [(-1, root)]
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        text = raw.split("#", 1)[0].rstrip()
        if not text.strip():
            continue
        indent = len(text) - len(text.lstrip(" "))
        if indent % 2:
            raise RunsError(f"{path}:{n}: indentation is two spaces a level")
        line = Line(tokens(text, f"{path}:{n}"), f"{path}:{n}")
        while stack[-1][0] >= indent:
            stack.pop()
        stack[-1][1].children.append(line)
        stack.append((indent, line))
    return root.children


# ------------------------------------------------------------- expressions

class Cursor:
    def __init__(self, toks: list[str], where: str):
        self.toks, self.i, self.where = toks, 0, where

    def peek(self, k: int = 0):
        return self.toks[self.i + k] if self.i + k < len(self.toks) else None

    def take(self, want: str | None = None) -> str:
        t = self.peek()
        if t is None or (want is not None and t != want):
            raise RunsError(f"{self.where}: expected {want or 'more'}, found {t!r}")
        self.i += 1
        return t

    def done(self) -> bool:
        return self.i >= len(self.toks)


BINARY = [("or",), ("and",), (), ("==", "!=", "<", "<=", ">", ">="), ("|",), ("^",), ("&",),
          ("<<", ">>"), ("+", "-")]


def expr(c: Cursor, level: int = 0):
    if level == 2:                                      # not
        if c.peek() == "not":
            c.take()
            return ("not", expr(c, 2))
        return expr(c, 3)
    if level == len(BINARY):
        return unary(c)
    left = expr(c, level + 1)
    while c.peek() in BINARY[level]:
        op = c.take()
        left = ("bin", op, left, expr(c, level + 1))
    return left


def unary(c: Cursor):
    if c.peek() in ("-", "~"):
        op = c.take()
        return ("neg", unary(c))
    return postfix(c)


def postfix(c: Cursor):
    e = primary(c)
    while True:
        if c.peek() == ".":
            c.take()
            e = ("field", e, c.take())
        elif c.peek() == "[":
            c.take()
            i = expr(c)
            c.take("]")
            e = ("index", e, i)
        elif c.peek() == "(" and e[0] == "name":
            c.take()
            args = []
            while c.peek() != ")":
                args.append(expr(c))
                if c.peek() == ",":
                    c.take()
            c.take(")")
            if e[1] not in BUILTINS and not instruction_call(e[1], args):
                raise RunsError(f"{c.where}: {e[1]} is not an operator of the word; a routine is run, not called")
            e = ("call", e[1], args)
        else:
            return e


def primary(c: Cursor):
    t = c.take()
    if t.isdigit():
        if t[0] == "0" and not set(t) <= set("01234567"):
            raise RunsError(f"{c.where}: {t} is not an octal number")
        return ("num", int(t, 8) if len(t) > 1 and t[0] == "0" else int(t))
    if t in ("true", "false"):
        return ("bool", t == "true")
    if t == "(":
        items = [expr(c)]
        while c.peek() == ",":
            c.take()
            items.append(expr(c))
        c.take(")")
        return items[0] if len(items) == 1 else ("tuple", items)
    if re.match(r"[A-Za-z_]", t):
        return ("name", t)
    raise RunsError(f"{c.where}: unexpected {t!r}")


def whole(toks: list[str], where: str):
    c = Cursor(toks, where)
    e = expr(c)
    if not c.done():
        raise RunsError(f"{where}: unexpected {c.peek()!r}")
    return e


# -------------------------------------------------------------- statements

def block(children: list[Line]) -> list:
    out, k = [], 0
    while k < len(children):
        line = children[k]
        t, where = line.toks, line.where
        head = t[0]
        if head == "if":
            arms = [(whole(t[1:-1], where), block(line.children))]
            other = []
            while k + 1 < len(children) and children[k + 1].toks[0] in ("elif", "else"):
                k += 1
                nxt = children[k]
                if nxt.toks[0] == "elif":
                    arms.append((whole(nxt.toks[1:-1], nxt.where), block(nxt.children)))
                else:
                    other = block(nxt.children)
            out.append(("if", arms, other, where))
        else:
            out.append(statement(line))
        k += 1
    return out


def statement(line: Line):
    t, where = line.toks, line.where
    head = t[0]
    if head in ("let", "set"):
        eq = t.index("=")
        target = whole(t[1:eq], where)
        return (head, target, whole(t[eq + 1:], where), where)
    if head == "loop":
        if t[1:3] != ["at", "most"] or t[-1] != ":":
            raise RunsError(f"{where}: loop at most N:")
        return ("loop", whole(t[3:-1], where), block(line.children), where)
    if head == "for":
        dots = t.index("..")
        return ("for", t[1], whole(t[3:dots], where), whole(t[dots + 1:-1], where),
                block(line.children), where)
    if head in ("break", "continue", "stop", "unreachable", "wait", "return"):
        if len(t) > 1:
            raise RunsError(f"{where}: {head} takes nothing after it")
        return (head, where)
    if head == "jump":
        if t[-3:-1] != ["at", "most"]:
            raise RunsError(f"{where}: jump <word of code> at most N")
        return ("jump", whole(t[1:-3], where), whole(t[-1:], where), where)
    if head == "emit":
        c = Cursor(t[3:], where)
        args = [expr(c)]
        while c.peek() == ",":
            c.take()
            args.append(expr(c))
        return ("emit", t[1], args, where)
    if head == "run" and line.children:
        if len(t) > 2:
            raise RunsError(f"{where}: a run passes wires, one a line, and nothing after its routine's name")
        wires = {}
        for w in line.children:
            if len(w.toks) < 3 or w.toks[1] != ":":
                raise RunsError(f"{w.where}: a wire is port: field")
            if w.toks[0] in wires:
                raise RunsError(f"{w.where}: {t[1]}'s {w.toks[0]} is wired twice")
            wires[w.toks[0]] = whole(w.toks[2:], w.where)
        return ("wire", t[1], wires, where)
    if head == "run":
        c = Cursor(t[2:], where)
        args = []
        if not c.done():
            c.take("(")
            while c.peek() != ")":
                args.append(expr(c))
                if c.peek() == ",":
                    c.take()
            c.take(")")
        if not c.done():
            raise RunsError(f"{where}: unexpected {c.peek()!r}")
        return ("run", t[1], args, where)
    if head == "match":
        arms = {}
        for arm in line.children:
            colon = arm.toks.index(":")
            body = [statement(Line(arm.toks[colon + 1:], arm.where))] if arm.toks[colon + 1:] \
                else block(arm.children)
            arms[arm.toks[0]] = body
        return ("match", whole(t[1:-1], where), arms, where)
    raise RunsError(f"{where}: unknown statement {head!r}")


# ------------------------------------------------------------ declarations

@dataclass
class Record:
    name: str
    count: int | None
    fields: dict[str, tuple[str, object]]          # name: (type, initial expr)
    stream: bool = False
    side: str | None = None                        # game, interface or presentation
    owner: str | None = None                       # the Network whose scratch it is (owns)


@dataclass(frozen=True)
class Port:
    """One value of a Processor's or Network's contract: the Network that
    runs it wires the Port to one field. `owns` is a Network's scratch."""
    direction: str                                 # in, out, inout, owns
    name: str
    type: str                                      # word, an enum, insn
    count: int | None = None                       # word[N]: the whole field of a collection


@dataclass
class Routine:
    kind: str                                      # processor, network
    name: str
    params: list[str]
    body: list
    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)
    requires: list = field(default_factory=list)
    ports: dict[str, Port] = field(default_factory=dict)
    owns: dict[str, Port] = field(default_factory=dict)


@dataclass
class Program:
    enums: dict[str, list[str]] = field(default_factory=dict)
    records: dict[str, Record] = field(default_factory=dict)
    routines: dict[str, Routine] = field(default_factory=dict)
    instructions: set[str] = field(default_factory=set)     # type insn: the instructions the game reaches
    display: str | None = None                              # type insn: the stream dpy plots on
    templates: dict[str, Routine] = field(default_factory=dict)    # the routines with Ports, as written
    copies: dict[str, tuple[str, tuple]] = field(default_factory=dict)  # copy -> (template, its wiring)

    def member(self, name: str) -> str | None:
        return next((e for e, ms in self.enums.items() if name in ms), None)


def params_of(toks: list[str]) -> list[str]:
    if "(" not in toks:
        return []
    inner = toks[toks.index("(") + 1:toks.index(")")]
    out, k = [], 0
    while k < len(inner):
        out.append(inner[k])
        k += 1
        while k < len(inner) and inner[k] != ",":
            k += 1
        k += 1
    return out


def machine_types(prog: Program, files: list[list[Line]]) -> None:
    """The machine description's `type insn`: the instructions the game
    reaches, and the stream dpy plots on. Read before anything is parsed."""
    for line in (line for f in files for line in f):
        if line.toks[:2] != ["type", "insn"]:
            continue
        for c in line.children:
            key, values = c.toks[0], c.toks[2:]
            if key == "instructions":
                if unknown := set(values) - set(OPERANDS):
                    raise RunsError(f"{c.where}: the machine has no rules for {sorted(unknown)}")
                prog.instructions = set(values)
            elif key == "display":
                prog.display = values[0]
    declared_instructions.clear()
    declared_instructions.update(prog.instructions)


def initial(c: Line, count: int | None):
    """A field's initial value: one expression, or, under a field of a
    collection that ends in `=`, one line a slot."""
    if "=" not in c.toks:
        return None
    eq = c.toks.index("=")
    if eq < len(c.toks) - 1:
        return whole(c.toks[eq + 1:], c.where)
    if len(c.children) != count:
        raise RunsError(f"{c.where}: {len(c.children)} initial values for {count} slots")
    return ("slots", [whole(v.toks, v.where) for v in c.children])


SIDES = ("game", "interface", "presentation")
PORT_HEADERS = ("in", "out", "inout", "owns")


def port_of(c: Line) -> Port:
    t = c.toks
    if len(t) == 4:
        return Port(t[0], t[1], t[3])
    if len(t) == 7 and t[4] == "[" and t[6] == "]" and t[5].isdigit():
        return Port(t[0], t[1], t[3], int(t[5], 8) if t[5].startswith("0") else int(t[5]))
    raise RunsError(f"{c.where}: a Port is `direction name: kind`, the kind a type or type[N]")


def owned_record(network: str) -> str:
    """The Record of a Network's scratch: its name is no name the text can
    write, so nothing outside the Network touches it."""
    return f"{network}$owns"


def substitute_names(tree, names: dict):
    if isinstance(tree, tuple):
        if len(tree) == 2 and tree[0] == "name" and tree[1] in names:
            return names[tree[1]]
        return tuple(substitute_names(x, names) for x in tree)
    if isinstance(tree, list):
        return [substitute_names(x, names) for x in tree]
    if isinstance(tree, dict):
        return {k: substitute_names(v, names) for k, v in tree.items()}
    return tree


def map_runs(tree, f):
    """The tree with each run and wire statement replaced by f of it."""
    if isinstance(tree, tuple) and tree[:1] in (("run",), ("wire",)):
        return f(tree)
    if isinstance(tree, tuple):
        return tuple(map_runs(x, f) for x in tree)
    if isinstance(tree, list):
        return [map_runs(x, f) for x in tree]
    if isinstance(tree, dict):
        return {k: map_runs(v, f) for k, v in tree.items()}
    return tree


def text_of(e) -> str:
    if e[0] == "name":
        return e[1]
    if e[0] == "num":
        return str(e[1])
    if e[0] == "field":
        return f"{text_of(e[1])}.{e[2]}"
    if e[0] == "index":
        return f"{text_of(e[1])}[{text_of(e[2])}]"
    if e[0] == "bin":
        return f"{text_of(e[2])} {e[1]} {text_of(e[3])}"
    return repr(e)


def kind_text(typ: str, count: int | None) -> str:
    return typ if count is None else f"{typ}[{count:o}]"


def wired_kind(prog: Program, e) -> tuple[str, int | None] | None:
    """The kind of the field a wire names: one slot, or the one word of a
    single Record, is its type; a whole field of a collection is type[N].
    None: no field."""
    base = e[1] if e[0] == "index" else e
    if not (base[0] == "field" and base[1][0] == "name" and base[1][1] in prog.records):
        return None
    rec = prog.records[base[1][1]]
    if rec.stream or base[2] not in rec.fields or e[0] == "index" and rec.count is None:
        return None
    return rec.fields[base[2]][0], None if e[0] == "index" else rec.count


def base_name(e) -> str | None:
    """The Port a wire or a target names, whole or at a slot."""
    if e[0] == "index":
        e = e[1]
    return e[1] if e[0] == "name" else None


def check_template(prog: Program, t: Routine) -> None:
    """A routine with Ports names no Record: its Ports are its contract."""
    if t.reads or t.writes:
        raise RunsError(f"{t.name}: its Ports are its contract; it declares no reads: or writes:")
    if t.params:
        raise RunsError(f"{t.name}: a routine with Ports takes no slot; its wires choose the field")
    if named := sorted(mentions([t.body, t.requires], set(prog.records))):
        raise RunsError(f"{t.name} names the Record {named[0]}; a routine with Ports touches only its Ports")
    own = set(t.ports) | set(t.owns)
    for s in walk_statements(t.body):
        if s[0] == "for" and s[1] in own:
            raise RunsError(f"{s[-1]}: {s[1]} is a Port of {t.name}, not a local")
        if s[0] in ("let", "set"):
            for x in s[1][1] if s[1][0] == "tuple" else [s[1]]:
                name = base_name(x)
                if s[0] == "let" and name in own:
                    raise RunsError(f"{s[-1]}: {name} is a Port of {t.name}, not a local")
                if s[0] == "set" and name in t.ports and t.ports[name].direction == "in":
                    raise RunsError(f"{s[-1]}: {t.name} sets {name}, an in Port")


def expand_ports(prog: Program) -> None:
    """Each run of a routine with Ports runs a copy of it: its text with each
    Port replaced by the field the run wires to it, as the original's macros
    were expanded at each use (`diff` once an axis). One copy a distinct
    wiring; a Network's Ports wired on to its runs resolve to the fields of
    the Network that runs it. A copy takes the names its wires' slots use
    (slot) from the routine that runs it."""
    for r in prog.routines.values():
        if r.owns and r.kind != "network":
            raise RunsError(f"{r.name}: only a Network owns scratch")
        for p in [*r.ports.values(), *r.owns.values()]:
            if p.name in prog.records:
                raise RunsError(f"{r.name}: its {p.direction} {p.name} has a Record's name")
            if p.type not in ("word", "insn") and p.type not in prog.enums:
                raise RunsError(f"{r.name}: {p.name}: no kind {p.type}")
            if p.direction == "owns" and p.count is not None:
                raise RunsError(f"{r.name}: owns {p.name}: scratch is one field, not {kind_text(p.type, p.count)}")
        if r.owns:
            rec = owned_record(r.name)
            prog.records[rec] = Record(rec, None, {p.name: (p.type, None) for p in r.owns.values()}, owner=r.name)
    prog.templates = {n: r for n, r in prog.routines.items() if r.ports}
    for t in prog.templates.values():
        check_template(prog, t)
    prog.routines = {n: r for n, r in prog.routines.items() if not r.ports}
    keys: dict[str, str] = {}
    taken = set(prog.routines) | set(prog.templates)

    def fill(owner: Routine, s):
        """A run of a routine with Ports, every Port wired: an omitted wire
        is the Port or scratch of the same name of the routine that runs it."""
        where = s[-1]
        t = prog.templates.get(s[1])
        if t is None:
            if s[0] == "wire":
                raise RunsError(f"{where}: {s[1]} has no Ports to wire")
            return s
        if s[0] == "run" and s[2]:
            raise RunsError(f"{where}: {t.name} has Ports: a run wires them and passes no slot")
        given = s[2] if s[0] == "wire" else {}
        if unknown := sorted(set(given) - set(t.ports)):
            raise RunsError(f"{where}: {t.name} has no Port {unknown[0]}")
        wires = {}
        for name, port in t.ports.items():
            if name in given:
                wires[name] = given[name]
            elif name in owner.ports or name in owner.owns:
                wires[name] = ("name", name)
            else:
                raise RunsError(f"{where}: run {t.name}: its Port {name} is not wired, and {owner.name} "
                                f"has no Port or scratch {name}")
            outer = owner.ports.get(base_name(wires[name]))
            if outer is not None and outer.direction == "in" and port.direction != "in":
                raise RunsError(f"{where}: run {t.name}: {name} is {port.direction}, wired to {owner.name}'s "
                                f"in Port {outer.name}")
        return ("wire", t.name, wires, where)

    def made(s, stack: tuple):
        if s[0] == "run":
            return s
        _, name, wires, where = s
        t = prog.templates[name]
        for p, e in wires.items():
            port = t.ports[p]
            got = wired_kind(prog, e)
            if got is None:
                raise RunsError(f"{where}: run {name}: {p} is wired to {text_of(e)}, which is no field")
            if got != (port.type, port.count):
                raise RunsError(f"{where}: run {name}: {p} is {kind_text(port.type, port.count)}, "
                                f"wired to {text_of(e)}, {kind_text(*got)}")
        free = []
        for e in wires.values():
            for n in sorted(names_read(e) - set(prog.records)):
                if n not in free and prog.member(n) is None:
                    free.append(n)
        key = repr((name, sorted(wires.items())))
        if key not in keys:
            if name in stack:
                raise RunsError(f"{name} fires itself: a recursion is a stack Record and a bounded Network loop")
            if clash := sorted(set(free) & (names_read(t.body) - set(t.ports))):
                raise RunsError(f"{where}: run {name}: its wires name {clash[0]}, which {name} names itself")
            k = 1
            while f"{name}_{k}" in taken:
                k += 1
            copy = f"{name}_{k}"
            taken.add(copy)
            keys[key] = copy
            prog.copies[copy] = (name, tuple(wires.items()))
            r = Routine(t.kind, copy, free, expanded(t, t.body, wires, stack + (name,)),
                        requires=substitute_names(t.requires, wires))
            if r.kind == "processor":
                read, written = touches(prog, r)
                r.reads, r.writes = read - written, written
            prog.routines[copy] = r
        return ("run", keys[key], [("name", n) for n in free], where)

    def expanded(owner: Routine, body: list, wires: dict, stack: tuple) -> list:
        names = {**wires, **{o: ("field", ("name", owned_record(owner.name)), o) for o in owner.owns}}
        body = substitute_names(map_runs(body, lambda s: fill(owner, s)), names)
        return map_runs(body, lambda s: made(s, stack))

    for r in list(prog.routines.values()):
        r.body = expanded(r, r.body, {}, (r.name,))
    for rec in prog.records.values():
        if rec.owner is not None:
            touching = [r.reads | r.writes for r in prog.routines.values()
                        if r.kind == "processor" and rec.name in r.reads | r.writes]
            shown = touching and all(any(prog.records[x].side == "presentation" for x in t) for t in touching)
            rec.side = "presentation" if shown else "game"



def load(paths: list[Path]) -> Program:
    prog = Program()
    files = [lines(path) for path in paths]
    machine_types(prog, files)
    for path, file in zip(paths, files):
        for line in file:
            t, where = line.toks, line.where
            side = None
            if t[0] in SIDES and t[1:2] in (["record"], ["stream"]):
                side, t = t[0], t[1:]
            kind = t[0]
            if kind == "type":
                continue
            if kind == "enum":
                prog.enums[t[1]] = [c.toks[0] for c in line.children]
            elif kind in ("record", "stream"):
                count = as_count(int(t[3], 8) if t[3].startswith("0") else int(t[3])) if len(t) > 2 else None
                fields = {c.toks[0]: (c.toks[2], initial(c, count)) for c in line.children}
                prog.records[t[1]] = Record(t[1], count, fields, kind == "stream", side)
            elif kind in ("processor", "network"):
                r = Routine(kind, t[1], params_of(t), [])
                body = []
                headers = ("reads", "writes", "requires")
                for c in line.children:
                    if c.toks[0] in PORT_HEADERS and c.toks[2:3] == [":"]:
                        port = port_of(c)
                        if port.name in r.ports or port.name in r.owns:
                            raise RunsError(f"{c.where}: {r.name} names {port.name} twice")
                        (r.owns if port.direction == "owns" else r.ports)[port.name] = port
                    elif c.toks[0] in headers and c.toks[1:2] == [":"]:
                        if c.toks[0] == "requires":
                            r.requires.append(whole(c.toks[2:], c.where))
                        else:
                            getattr(r, c.toks[0]).update(x for x in c.toks[2:] if x != ",")
                    else:
                        body.append(c)
                r.body = block(body)
                if r.name in prog.routines:
                    raise RunsError(f"{where}: {r.name} defined twice")
                prog.routines[r.name] = r
            else:
                raise RunsError(f"{where}: unknown declaration {kind!r}")
    expand_ports(prog)
    return prog


NETWORK_OPS = {"if", "for", "match", "run", "stop", "unreachable", "loop", "break", "wait"}
FIRING_OPS = {"run", "stop", "match", "wait"}


def guarded_exit(stmt) -> bool:
    """An `if` with an arm that ends in break: an exit of a network loop."""
    return stmt[0] == "if" and any(body and body[-1][0] == "break"
                                   for body in [b for _, b in stmt[1]] + [stmt[2]])


def shape(stmts: list, r: Routine, in_loop: bool):
    """What each kind may say, checked over the whole body before anything runs.
    A network writes nothing: it has no let, set, emit or return. Its loop is
    bounded and leaves only through an `if` on Records that breaks."""
    for k, s in enumerate(stmts):
        op, where = s[0], s[-1]
        if op in ("break", "continue", "return", "stop", "unreachable") and k + 1 < len(stmts):
            raise RunsError(f"{stmts[k + 1][-1]}: nothing after {op} runs")
        if r.kind == "network":
            if op not in NETWORK_OPS:
                raise RunsError(f"{where}: a network only fires and chooses ({op})")
            if op == "loop" and not any(guarded_exit(x) for x in s[2]):
                raise RunsError(f"{where}: a network loop needs an exit: an if with an arm that ends in break")
        elif op in FIRING_OPS:
            raise RunsError(f"{where}: {op} belongs to a network")
        if op in ("break", "continue") and not in_loop:
            raise RunsError(f"{where}: {op} outside a loop")
        if op == "if":
            for _, body in s[1]:
                shape(body, r, in_loop)
            shape(s[2], r, in_loop)
        elif op in ("loop", "for"):
            shape(s[-2], r, in_loop=in_loop or op == "loop")
        elif op == "match":
            for body in s[2].values():
                shape(body, r, in_loop)


# --------------------------------------------------------------- execution

class Break(Exception): pass
class Continue(Exception): pass
class Stop(Exception): pass


class Return(Exception): pass


class NotPorted(RunsError):
    pass


class StopAt(Exception):
    def __init__(self, name):
        self.name = name


class Unknown:
    """The value of a field with no initial value, until the game sets it or
    the world gives it."""

    def __repr__(self) -> str:
        return "unknown"

    def __deepcopy__(self, memo):
        return self                     # one unknown: a copied state still holds UNKNOWN


UNKNOWN = Unknown()


@dataclass(frozen=True)
class Member:
    enum: str
    name: str


class Machine:
    """The Records and a Program to run over them."""

    def __init__(self, prog: Program):
        self.prog = prog
        self.state: dict[str, object] = {}
        self.stop_before: set[str] = set()
        self.fired: list[tuple[str, tuple]] = []
        self.on_wait = lambda machine: None     # the host's turn at a wait
        self.jumped_to: str | None = None       # the routine code jumped to as it left
        # The locals each Processor's last firing left, by (name, arguments):
        # a check compares them with the words the original keeps them in.
        self.left: dict[tuple, dict] = {}
        # When each field was last written, in writes since the Machine began:
        # a check reads a word the binding shares by the name that wrote it last.
        self.written: dict[tuple[str, str], int] = {}
        self.writes = 0
        declared_instructions.clear()
        declared_instructions.update(prog.instructions)
        for rec in prog.records.values():
            self.state[rec.name] = [] if rec.stream else self.fresh(rec)

    def fresh(self, rec: Record):
        def init(e, typ):
            return self.typed(self.eval(e, Scope("initial", {})), typ) if e is not None else UNKNOWN

        def slots(e, typ):
            if e is not None and e[0] == "slots":
                return [init(x, typ) for x in e[1]]
            return [init(e, typ) for _ in range(rec.count)]
        if rec.count is None:
            return {f: init(e, typ) for f, (typ, e) in rec.fields.items()}
        return {f: slots(e, typ) for f, (typ, e) in rec.fields.items()}

    # ---- running

    def run(self, name: str, args=()):
        r = self.prog.routines.get(name)
        if name in self.stop_before:
            raise StopAt(name)
        if r is None:
            raise NotPorted(f"{name} is not ported")
        self.fired.append((name, tuple(args)))
        scope = Scope(r.kind, dict(zip(r.params, args)), r)
        for cond in r.requires:
            if not self.truth(self.eval(cond, scope)):
                raise RunsError(f"{name}{tuple(args)}: precondition fails")
        try:
            self.block(r.body, scope)
        except Return:
            pass
        except (Break, Continue):
            raise RunsError(f"{name}: break or continue outside a loop")
        if r.kind == "processor":
            self.left[(name, tuple(args))] = scope.locals

    def block(self, stmts: list, scope: "Scope"):
        for k, s in enumerate(stmts):
            self.stmt(s, scope)
            if self.jumped_to is not None and scope.kind == "network":
                nxt = stmts[k + 1] if k + 1 < len(stmts) else None
                if not (nxt and nxt[0] == "run" and nxt[1] == self.jumped_to):
                    raise RunsError(f"{s[-1]}: the code jumped to {self.jumped_to}, so the Network runs it next")
                self.jumped_to = None

    def stmt(self, s, scope: "Scope"):
        op = s[0]
        if op == "if":
            _, arms, other, _ = s
            for cond, body in arms:
                if self.truth(self.eval(cond, scope)):
                    return self.block(body, scope)
            return self.block(other, scope)
        if op == "let":
            _, target, e, where = s
            self.bind(target, self.eval(e, scope), scope, where, new=True)
        elif op == "set":
            _, target, e, where = s
            self.bind(target, self.eval(e, scope), scope, where, new=False)
        elif op == "loop":
            _, bound, body, where = s
            n = self.bound(bound, scope, where)
            for _ in range(n):
                try:
                    self.block(body, scope)
                except Break:
                    return
                except Continue:
                    pass
            raise RunsError(f"{where}: loop ran past its bound of {n}")
        elif op == "for":
            _, var, lo, hi, body, _ = s
            for i in range(as_count(self.eval(lo, scope)), as_count(self.eval(hi, scope)) + 1):
                scope.locals[var] = i
                self.block(body, scope)
        elif op == "break":
            raise Break()
        elif op == "continue":
            raise Continue()
        elif op == "return":
            raise Return()
        elif op == "emit":
            _, name, args, _ = s
            scope.check(name, write=True)
            rec = self.prog.records[name]
            vals = [self.eval(a, scope) for a in args]
            self.state[name].append(tuple(as_count(v) if t == "int" else as_word(v)
                                          for v, (t, _) in zip(vals, rec.fields.values())))
        elif op == "run":
            _, name, args, _ = s
            self.run(name, [self.eval(a, scope) for a in args])
        elif op == "match":
            _, e, arms, where = s
            v = self.eval(e, scope)
            enum = self.prog.enums[v.enum]
            missing = set(enum) - set(arms)
            if missing:
                raise RunsError(f"{where}: match misses {sorted(missing)}")
            self.block(arms[v.name], scope)
        elif op == "stop":
            raise Stop()
        elif op == "wait":
            self.on_wait(self)
        elif op == "jump":
            _, target, bound, where = s
            rec, fld, at = self.place(target, scope, where)
            if at is None:
                raise RunsError(f"{where}: code is a slot of a collection")
            self.jumped_to = self.execute(Place(rec, fld, at), self.bound(bound, scope, where), scope, where)
        elif op == "unreachable":
            raise RunsError(f"{s[1]}: reached unreachable")

    def bound(self, e, scope: "Scope", where: str) -> int:
        if e[0] == "num":
            return e[1]                         # a count, though it may not fit a word's sign (0400001)
        try:
            return as_count(self.eval(e, scope))
        except RunsError as x:
            raise RunsError(f"{where}: the bound is no count: {x}") from None

    def truth(self, v) -> bool:
        if not isinstance(v, bool):
            raise RunsError(f"not a condition: {v!r}")
        return v

    # ---- binding

    def bind(self, target, value, scope: "Scope", where: str, new: bool):
        if target[0] == "tuple":
            if not isinstance(value, tuple) or len(value) != len(target[1]):
                raise RunsError(f"{where}: cannot spread {value!r}")
            for t, v in zip(target[1], value):
                self.bind(t, v, scope, where, new)
            return
        if target[0] == "name":
            if not new and target[1] not in scope.locals:
                raise RunsError(f"{where}: set {target[1]} before let")
            scope.locals[target[1]] = value
            return
        if new:
            raise RunsError(f"{where}: let binds a local name")
        rec, fld, idx = self.place(target, scope, where)
        scope.check(rec, write=True)
        typ = self.prog.records[rec].fields[fld][0]
        value = self.typed(value, typ)
        if typ == "word":
            value = as_word(value)
        elif typ == "insn" and not isinstance(value, Insn):
            raise RunsError(f"{where}: {rec}.{fld} holds an instruction, not {value!r}")
        elif typ in self.prog.enums and not (isinstance(value, Member) and value.enum == typ):
            raise RunsError(f"{where}: {rec}.{fld} holds {typ}, not {value!r}")
        if idx is None:
            self.state[rec][fld] = value
        else:
            self.state[rec][fld][idx] = value
        self.writes += 1
        self.written[(rec, fld)] = self.writes

    def place(self, target, scope: "Scope", where: str):
        if target[0] == "field" and target[1][0] == "name" and target[1][1] in self.prog.records:
            return target[1][1], target[2], None
        if target[0] == "index" and target[1][0] == "field" and target[1][1][0] == "name":
            rec, fld = target[1][1][1], target[1][2]
            return rec, fld, slot(self.state[rec][fld], as_count(self.eval(target[2], scope)), target)
        raise RunsError(f"{where}: not a Record field")

    # ---- expressions

    def eval(self, e, scope: "Scope"):
        op = e[0]
        if op == "num":
            return word_of(e[1])
        if op == "bool":
            return e[1]
        if op == "tuple":
            return tuple(self.eval(x, scope) for x in e[1])
        if op == "name":
            n = e[1]
            if n in scope.locals:
                return scope.locals[n]
            if n in self.prog.records:
                scope.check(n, write=False)
                return ("record", n)
            enum = self.prog.member(n)
            if enum:
                return Member(enum, n)
            if n in self.prog.instructions and OPERANDS[n] is None:
                return Insn(n)
            raise RunsError(f"unknown name {n}")
        if op == "field":
            base = self.eval(e[1], scope)
            if not (isinstance(base, tuple) and base[:1] == ("record",)):
                raise RunsError(f"{e[2]}: field of a non-Record")
            return known(self.state[base[1]][e[2]], f"{base[1]}.{e[2]}")
        if op == "index":
            seq = self.eval(e[1], scope)
            return known(seq[slot(seq, as_count(self.eval(e[2], scope)), e)], repr(e[1]))
        if op == "call" and instruction_call(e[1], e[2]):
            return Insn(e[1], self.operand(e[1], e[2][0], scope))
        if op == "call":
            return BUILTINS[e[1]](*[self.eval(a, scope) for a in e[2]])
        if op == "neg":
            return W(as_word(self.eval(e[1], scope)).v ^ MASK)
        if op == "not":
            return not self.truth(self.eval(e[1], scope))
        if op == "bin":
            _, o, l, r = e
            if o == "and":
                return self.truth(self.eval(l, scope)) and self.truth(self.eval(r, scope))
            if o == "or":
                return self.truth(self.eval(l, scope)) or self.truth(self.eval(r, scope))
            a, b = self.eval(l, scope), self.eval(r, scope)
            if isinstance(a, Member) and isinstance(b, Member):
                b = self.typed(b, a.enum)
            return binary(o, a, b)
        raise RunsError(f"cannot evaluate {e!r}")

    def operand(self, op: str, e, scope: "Scope"):
        """An instruction's operand: the word of a Record it names (its slot
        computed now, the word itself not read), a routine, or a number."""
        kind = OPERANDS[op]
        if kind == "number":
            if e[0] != "num":
                raise RunsError(f"{op} takes a number: {e!r}")
            return e[1]
        if kind == "target" and e[0] == "name" and e[1] in self.prog.routines:
            return e[1]
        if e[0] == "field" and e[1][0] == "name" and e[1][1] in self.prog.records:
            rec, fld, slot = e[1][1], e[2], None
        elif e[0] == "index" and e[1][0] == "field" and e[1][1][0] == "name":
            rec, fld, slot = e[1][1][1], e[1][2], as_count(self.eval(e[2], scope))
        else:
            raise RunsError(f"{op} names a word of a Record{' or a routine' if kind == 'target' else ''}: {e!r}")
        r = self.prog.records.get(rec)
        if r is None or fld not in r.fields or (slot is None) != (r.count is None) \
                or slot is not None and slot >= r.count:
            raise RunsError(f"{op}: no word {rec}.{fld}{'' if slot is None else f'[{slot:o}]'}")
        return Place(rec, fld, slot)

    # ---- code

    def execute(self, start: Place, bound: int, scope: "Scope", where: str) -> str:
        """Run the words of code from start by the PDP-1's rules, until a
        jump leaves for a routine: its name. AC, IO and the program flags
        are the code's own, unknown until it sets them. The words it reads
        and writes go through the running Processor's contract."""
        ac = io = UNKNOWN
        flags: dict[int, bool] = {}
        pc = start.slot

        def read(at: Place):
            scope.check(at.record, write=False)
            v = self.state[at.record][at.field]
            return known(v if at.slot is None else v[at.slot], f"{at.record}.{at.field}")

        def write(at: Place, value):
            scope.check(at.record, write=True)
            if self.prog.records[at.record].fields[at.field][0] != "word":
                raise RunsError(f"{where}: {at.record}.{at.field} is not a word")
            if at.slot is None:
                self.state[at.record][at.field] = value
            else:
                self.state[at.record][at.field][at.slot] = value
            self.writes += 1
            self.written[(at.record, at.field)] = self.writes

        for _ in range(bound):
            insn = read(Place(start.record, start.field, pc))
            if not isinstance(insn, Insn):
                raise RunsError(f"{where}: {start.record}.{start.field}[{pc:o}] is not an instruction")
            pc += 1
            op, x = insn.op, insn.operand
            if op == "lac":
                ac = as_word(read(x))
            elif op == "lio":
                io = as_word(read(x))
            elif op == "dac":
                write(x, known(ac, "AC"))
            elif op == "dio":
                write(x, known(io, "IO"))
            elif op == "add":
                ac = add(known(ac, "AC"), as_word(read(x)))
            elif op == "sub":
                ac = sub(known(ac, "AC"), as_word(read(x)))
            elif op == "cma":
                ac = W(known(ac, "AC").v ^ MASK)
            elif op == "rcl":
                ac, io = rcl(known(ac, "AC"), known(io, "IO"), x)
            elif op in ("stf", "clf"):
                flags[x] = op == "stf"
            elif op == "szf":
                if not known(flags.get(x, UNKNOWN), f"program flag {x}"):
                    pc += 1
            elif op == "ioh":
                pass                                    # waits for the display: timing
            elif op == "dpy":
                scope.check(self.prog.display, write=True)
                self.state[self.prog.display].append((known(ac, "AC"), known(io, "IO"), 0))
            elif op == "jmp" and isinstance(x, str):
                return x
            elif op == "jmp":
                if (x.record, x.field) != (start.record, start.field):
                    raise RunsError(f"{where}: a jump from {start.record}.{start.field} to {x.record}.{x.field}")
                pc = x.slot
            else:
                raise RunsError(f"{where}: the machine has no rule for {op}")
        raise RunsError(f"{where}: the code ran past {bound} instructions")

    def typed(self, value, enum: str):
        """A member's name is the member of the enum it is compared with or
        stored as, when two enums share the name (off, on)."""
        if isinstance(value, Member) and value.enum != enum and value.name in self.prog.enums.get(enum, []):
            return Member(enum, value.name)
        return value


def slot(seq: list, n: int, e) -> int:
    """A slot of a collection: reading or writing past its last is an error."""
    if n >= len(seq):
        raise RunsError(f"{e!r}: slot {n:o} is past the collection's {len(seq):o} slots")
    return n


def known(value, what: str):
    if value is UNKNOWN:
        raise RunsError(f"{what} is unknown: the game has not set it, so the world gives it")
    return value


def binary(o: str, a, b):
    if isinstance(a, Member) or isinstance(b, Member):
        if o not in ("==", "!="):
            raise RunsError(f"{o} on enum")
        return (a == b) == (o == "==")
    index = any(isinstance(x, int) and not isinstance(x, bool) for x in (a, b))
    if index and o in ("+", "-", "==", "!=", "<", "<=", ">", ">="):
        a, b = as_count(a), as_count(b)
        return {"+": a + b, "-": a - b, "==": a == b, "!=": a != b, "<": a < b, "<=": a <= b,
                ">": a > b, ">=": a >= b}[o]
    if o in ("<", "<=", ">", ">="):
        w, z = as_word(a), as_word(b)
        if z.v != 0:
            raise RunsError("a word compares with 0 only")
        neg = bool(w.v & SIGN)
        return {"<": neg, ">=": not neg, "<=": neg or w.v == 0, ">": not (neg or w.v == 0)}[o]
    if o in ("<<", ">>"):
        return (sal if o == "<<" else sar)(as_word(a), as_count(b))
    a, b = as_word(a), as_word(b)
    if o == "==":
        return a.v == b.v
    if o == "!=":
        return a.v != b.v
    if o == "+":
        return add(a, b)
    if o == "-":
        return sub(a, b)
    if o == "&":
        return W(a.v & b.v)
    if o == "|":
        return W(a.v | b.v)
    if o == "^":
        return W(a.v ^ b.v)
    raise RunsError(f"no word operator {o}")


@dataclass
class Scope:
    kind: str
    locals: dict
    routine: Routine | None = None

    def check(self, record: str, write: bool):
        if self.kind == "initial":
            raise RunsError(f"an initial value touches no Record ({record})")
        if self.kind == "network":
            if write:
                raise RunsError(f"a network writes no Record ({record})")
            return
        r = self.routine
        if record not in r.writes and (write or record not in r.reads):
            raise RunsError(f"{r.name} does not declare {'writes' if write else 'reads'}: {record}")


def program_dir() -> Path:
    """The program's directory: the repo's root (Spacewar), or RUNS_PROGRAM,
    relative to the root, for another program (programs/minskytron)."""
    import os
    root = Path(__file__).resolve().parents[1]
    return (root / os.environ.get("RUNS_PROGRAM", ".")).resolve()


def source() -> Path:
    """The RUNS source to run: the program's runs/, or RUNS_SOURCE when a check runs a variant."""
    import os
    return Path(os.environ.get("RUNS_SOURCE", program_dir() / "runs"))


def mentions(tree, names: set[str]) -> set[str]:
    """The names a statement or expression tree mentions. An instruction
    names a word it does not read: only its slot's expression counts."""
    if isinstance(tree, str):
        return {tree} & names
    if isinstance(tree, tuple) and tree[:1] == ("field",):
        return mentions(tree[1], names)         # a field's own name mentions nothing
    if isinstance(tree, tuple) and tree[:1] == ("call",) and instruction_call(tree[1], tree[2]):
        return mentions([tree[2][0][2]] if tree[2] and tree[2][0][0] == "index" else [], names)
    if isinstance(tree, (list, tuple)):
        return set().union(*(mentions(t, names) for t in tree)) if tree else set()
    if isinstance(tree, dict):
        return mentions(list(tree.values()), names)
    return set()


def runs_of(tree) -> set[str]:
    """The routines a body's run statements name."""
    if isinstance(tree, tuple) and tree and tree[0] == "run":
        return {tree[1]}
    if isinstance(tree, (list, tuple)):
        return set().union(*(runs_of(t) for t in tree)) if tree else set()
    if isinstance(tree, dict):
        return runs_of(list(tree.values()))
    return set()


def fires(prog: Program, name: str, seen: set[str]) -> set[str]:
    """Every routine a routine fires, itself included, through its sub-Networks."""
    if name in seen or name not in prog.routines:
        return seen
    seen.add(name)
    for target in runs_of(prog.routines[name].body):
        fires(prog, target, seen)
    return seen


def reads_of(tree, records: set[str]) -> set[str]:
    """The Records a body reads: every Record it mentions, except as the
    Record a set writes."""
    if isinstance(tree, tuple) and tree and tree[0] == "set":
        target = tree[1]
        targets = target[1] if target[0] == "tuple" else [target]
        inner = [t[2] for t in targets if t[0] == "index"]
        return mentions(tree[2], records) | mentions(inner, records)
    if isinstance(tree, tuple) and tree[:1] == ("field",):
        return mentions(tree, records)
    if isinstance(tree, (list, tuple)):
        return set().union(*(reads_of(s, records) for s in tree)) if tree else set()
    return mentions(tree, records)


def check_inputs(prog: Program, n: Routine, inside: set[str]) -> None:
    """A field with no initial value comes in from outside the game: a top
    Network whose routines read its Record declares it under reads:."""
    unknown = {name for name, r in prog.records.items()
               if not r.stream and r.owner is None and any(e is None for _, e in r.fields.values())}
    for name in sorted(inside):
        r = prog.routines[name]
        for rec in sorted(reads_of(r.body, unknown) - n.reads):
            raise RunsError(f"network {n.name}: {rec} comes in from outside the game ({r.name} reads it "
                            f"and it has fields with no initial value); declare reads: {rec}")


def presentation_routines(prog: Program) -> set[str]:
    """The presentation's routines: each Processor that touches a
    presentation Record, and each Network that runs only those."""
    side = {n: r.side for n, r in prog.records.items()}
    out = {n for n, r in prog.routines.items()
           if r.kind == "processor" and any(side.get(x) == "presentation" for x in r.reads | r.writes)}
    while True:
        more = {n for n, r in prog.routines.items()
                if r.kind == "network" and n not in out and runs_of(r.body) and runs_of(r.body) <= out}
        if not more:
            return out
        out |= more


def impurities(prog: Program) -> list[str]:
    """Every place the text is not yet pure. Each Record is the game's, the
    interface's, or the presentation's. The presentation reads the interface
    and nothing of the game's, and writes only its own Records, so the game's
    Records are the same with the presentation removed and a platform
    replaces it whole."""
    side = {n: r.side for n, r in prog.records.items()}
    out = [f"{n}: say whether it is a game, interface or presentation record"
           for n, s in side.items() if s is None]
    out += [f"stream {r.name}: a stream leaves to a device, so it is a presentation stream"
            for r in prog.records.values() if r.stream and r.side not in (None, "presentation")]
    out += [f"{r.name}.{f}: a Record holds data; instructions a Processor runs are logic"
            for r in prog.records.values() for f, (typ, _) in r.fields.items() if typ == "insn"]
    out += [f"processor {r.name}: runs instructions from a Record (jump); its logic belongs in its own text"
            for r in prog.routines.values()
            if r.kind == "processor" and any(s[0] == "jump" for s in walk_statements(r.body))]
    of = lambda names, s: sorted(n for n in names if side.get(n) == s)
    for r in prog.routines.values():
        if r.kind != "processor":
            continue
        shown = of(r.reads | r.writes, "presentation")
        if not shown:
            continue
        if game := of(r.reads | r.writes, "game"):
            out.append(f"processor {r.name}: touches the presentation's {shown[0]} and the game's {game[0]}; "
                       f"split it, or give the game's value to an interface record")
        if written := of(r.writes, "interface"):
            out.append(f"processor {r.name}: the presentation writes the interface record {written[0]}; "
                       f"only the game and the world write it")
    shown = presentation_routines(prog)
    presentation = {n for n, s in side.items() if s == "presentation"}

    def guarded(name: str, stmts: list):
        for s in stmts:
            op = s[0]
            if op == "if":
                guards, bodies = [c for c, _ in s[1]], [b for _, b in s[1]] + [s[2]]
            elif op == "loop":
                guards, bodies = [s[1]], [s[2]]
            elif op == "for":
                guards, bodies = [s[2], s[3]], [s[4]]
            elif op == "match":
                guards, bodies = [s[1]], list(s[2].values())
            else:
                continue
            read = mentions(guards, presentation)
            game = sorted(runs_of(bodies) - shown)
            if read and game:
                out.append(f"network {name}: a guard reads the presentation's {sorted(read)[0]}, "
                           f"and the game's {game[0]} runs under it")
            for b in bodies:
                guarded(name, b)

    for r in prog.routines.values():
        if r.kind == "network":
            guarded(r.name, r.body)
            for s in walk_statements(r.body):
                guards = [c for c, _ in s[1]] if s[0] == "if" else [s[1]] if s[0] == "match" else []
                if any(computes(g) for g in guards):
                    out.append(f"network {r.name}: a guard computes ({s[-1].rsplit('/', 1)[-1]}); "
                               f"a Processor computes the value into a Record and the guard tests it")
                if s[0] == "run" and s[1] in prog.routines:
                    for arg, param in zip(s[2], prog.routines[s[1]].params):
                        if not label_only(prog, s[1], param, set()):
                            out.append(f"network {r.name}: run {s[1]} passes {param} as a value "
                                       f"({s[-1].rsplit('/', 1)[-1]}); a value goes through a Record")
    return out


COMPARE = {"==", "!=", "<", "<=", ">", ">=", "and", "or"}


def computes(e) -> bool:
    """Whether a guard computes on a Record's value. Comparisons, and, or
    and not only test; arithmetic inside a slot (which object) is a label."""
    if not isinstance(e, tuple) or not e:
        return False
    op = e[0]
    if op in ("name", "num", "field"):
        return False
    if op == "index":
        return computes(e[1])
    if op == "not":
        return computes(e[1])
    if op == "bin":
        return e[1] not in COMPARE or computes(e[2]) or computes(e[3])
    return True


def label_only(prog: Program, routine: str, param: str, seen: set) -> bool:
    """Whether a routine uses a parameter only to say which slot: inside a
    collection's index, a requires:, a loop's bounds, or passed on to a
    routine that uses it the same way."""
    if (routine, param) in seen:
        return True
    seen.add((routine, param))
    r = prog.routines[routine]

    def uses(tree, as_label: bool) -> bool:
        if isinstance(tree, tuple) and tree:
            if tree == ("name", param):
                return as_label
            if tree[0] == "index":
                return uses(tree[1], as_label) and uses(tree[2], True)
            if tree[0] == "run" and tree[1] in prog.routines:
                callee = prog.routines[tree[1]].params
                return all(not mentions(a, {param}) or label_only(prog, tree[1], p, seen)
                           for a, p in zip(tree[2], callee))
            if tree[0] == "for":
                return uses(tree[2], True) and uses(tree[3], True) and uses(tree[4], as_label)
            return all(uses(x, as_label) for x in tree[1:])
        if isinstance(tree, list):
            return all(uses(x, as_label) for x in tree)
        if isinstance(tree, dict):
            return all(uses(x, as_label) for x in tree.values())
        return True

    return uses(r.body, False)


def without_presentation(prog: Program) -> Program:
    """The game alone: the program with every presentation routine, every
    run of one, and every presentation Record removed. A pure program's
    game Records fire the same in it as in the whole program."""
    import copy
    shown = presentation_routines(prog)
    kept = {n for n, r in prog.records.items() if r.side != "presentation"}

    def strip(stmts: list) -> list:
        out = []
        for s in stmts:
            op = s[0]
            if op == "run" and s[1] in shown:
                continue
            if op == "if":
                s = (op, [(c, strip(b)) for c, b in s[1]], strip(s[2]), *s[3:])
            elif op == "loop":
                s = (op, s[1], strip(s[2]), *s[3:])
            elif op == "for":
                s = (op, s[1], s[2], s[3], strip(s[4]), *s[5:])
            elif op == "match":
                s = (op, s[1], {m: strip(b) for m, b in s[2].items()}, *s[3:])
            out.append(s)
        return out

    game = copy.deepcopy(prog)
    game.records = {n: r for n, r in game.records.items() if n in kept}
    game.routines = {n: r for n, r in game.routines.items() if n not in shown}
    for r in game.routines.values():
        if r.kind == "network":
            r.body = strip(r.body)
            r.reads &= kept
            r.writes &= kept
    return game


def check_sides(prog: Program) -> None:
    """A program is pure, or it is an error: every Record has a kind, and
    the kind rules hold. tools/check_purity.py reads a text that is not yet
    pure (check with sides=False) and lists every impurity."""
    if found := impurities(prog):
        raise RunsError(found[0])


def check_contracts(prog: Program) -> None:
    """A Network that declares reads or writes states its contract with the
    world outside it, as a Processor does. A top Network, one that nothing
    fires, is a whole game: it always has a contract, its boundary with
    presentation. Every Record a Network's Processors touch is its own,
    unless a Processor it does not fire touches it too, or it is a stream:
    those cross its boundary and must be declared. A Processor that nothing
    fires (a tunable whose caller is not ported yet) shares nothing at run
    time. Each declared Record must be touched inside.

    A game may have several top Networks: the start Networks, which the
    host fires once, and the frame, which it fires each frame. Together
    they are the game, so a Record they share does not cross the boundary."""
    records = set(prog.records)
    fired = set().union(*(runs_of(r.body) - {r.name} for r in prog.routines.values()))
    tops = [n.name for n in prog.routines.values() if n.kind == "network" and n.name not in fired]
    game = set().union(*(fires(prog, t, set()) for t in tops))
    game_read = set().union(*(touches(prog, prog.routines[r])[0] for r in game))
    for n in prog.routines.values():
        if n.kind != "network" or not (n.reads or n.writes or n.name not in fired):
            continue
        inside = fires(prog, n.name, set())
        procs = [prog.routines[r] for r in inside if prog.routines[r].kind == "processor"]
        read = set().union(*(p.reads | p.writes for p in procs))
        written = set().union(*(p.writes for p in procs))
        guarded = set().union(*(mentions(prog.routines[r].body, records) for r in inside
                                if prog.routines[r].kind == "network"))
        outside = [r for name, r in prog.routines.items()
                   if name not in inside and name in fired and r.kind == "processor"
                   and (n.name in fired or name not in game)]
        shared = set().union(*(p.reads | p.writes for p in outside))
        for rec in sorted(written & (shared | {r for r in records if prog.records[r].stream})):
            if rec not in n.writes:
                raise RunsError(f"network {n.name}: {rec} leaves it; declare writes: {rec}")
        for rec in sorted((read | guarded) - written & shared):
            if rec not in n.reads and rec not in n.writes:
                raise RunsError(f"network {n.name}: {rec} comes from outside it; declare reads: {rec}")
        if stale := sorted(n.writes - written):
            raise RunsError(f"network {n.name} declares writes: {stale}, but nothing inside writes them")
        if stale := sorted(n.reads - read - guarded):
            raise RunsError(f"network {n.name} declares reads: {stale}, but nothing inside reads them")
        if n.name not in fired:
            check_inputs(prog, n, inside)
            for rec in sorted(written - game_read - n.writes):
                raise RunsError(f"network {n.name}: nothing in the game reads {rec}, so it leaves the game; "
                                f"declare writes: {rec}")


def check_scope(prog: Program, r: Routine) -> None:
    """Every name a routine's text uses means something where it stands,
    checked before anything runs: a local is let before it is read or set
    on every path that reaches it, a field is a field of its Record, a run
    names a routine with its arguments, and a Processor touches only the
    Records it declares."""
    where = r.name

    def fail(at: str, what: str):
        raise RunsError(f"{at}: {what}")

    def place(e, at: str, defined: set[str], write: bool):
        """A Record field, or a slot of one, as an expression or a target."""
        base = e[1] if e[0] == "index" else e
        if not (base[0] == "field" and base[1][0] == "name" and base[1][1] in prog.records):
            fail(at, f"not a Record field: {e!r}")
        rec = prog.records[base[1][1]]
        if base[2] not in rec.fields:
            fail(at, f"{rec.name} has no field {base[2]}")
        if (e[0] == "index") != (rec.count is not None) or rec.stream:
            fail(at, f"{rec.name}.{base[2]} is {'a collection' if rec.count else 'one word'}")
        if e[0] == "index":
            slot_of(rec, e[2], at)
            expr(e[2], at, defined)
        if r.kind == "processor" and rec.name not in r.writes and (write or rec.name not in r.reads):
            fail(at, f"{r.name} does not declare {'writes' if write else 'reads'}: {rec.name}")

    def slot_of(rec: Record, e, at: str):
        if e[0] == "num" and e[1] >= rec.count:
            fail(at, f"{rec.name} has {rec.count} slots, not slot {e[1]:o}")

    def expr(e, at: str, defined: set[str]):
        op = e[0]
        if op == "num" and e[1] > MASK:
            fail(at, f"{e[1]:o} does not fit a word")
        if op in ("num", "bool"):
            return
        if op == "name":
            n = e[1]
            if n not in defined and prog.member(n) is None and not (n in prog.instructions and OPERANDS[n] is None):
                fail(at, f"unknown name {n}" + (" (a Record is read by its fields)" if n in prog.records else ""))
        elif op in ("field", "index"):
            place(e, at, defined, write=False)
        elif op == "call" and instruction_call(e[1], e[2]):
            x = e[2][0] if e[2] else None
            kind = OPERANDS[e[1]]
            if kind == "number" and x[0] != "num":
                fail(at, f"{e[1]} takes a number")
            elif kind == "target" and x[0] == "name" and x[1] in prog.routines:
                pass
            elif kind in ("place", "target"):
                base = x[1] if x[0] == "index" else x
                if not (base[0] == "field" and base[1][0] == "name" and base[1][1] in prog.records
                        and base[2] in prog.records[base[1][1]].fields):
                    fail(at, f"{e[1]} names a word of a Record{' or a routine' if kind == 'target' else ''}")
                if x[0] == "index":
                    slot_of(prog.records[base[1][1]], x[2], at)
                    expr(x[2], at, defined)
        elif op == "call":
            if e[1] in BUILTINS and len(e[2]) != (n := BUILTINS[e[1]].__code__.co_argcount):
                fail(at, f"{e[1]} takes {n} values, not {len(e[2])}")
            for a in e[2]:
                expr(a, at, defined)
        elif op in ("neg", "not"):
            expr(e[1], at, defined)
        elif op == "bin":
            if e[1] in ("<", "<=", ">", ">=") and e[3] != ("num", 0) \
                    and not (e[2][0] == "name" and e[2][1] in counts):
                fail(at, f"{e[1]} compares a word with 0 only, or a slot or count with a number")
            expr(e[2], at, defined)
            expr(e[3], at, defined)
        elif op == "tuple":
            for x in e[1]:
                expr(x, at, defined)
        else:
            fail(at, f"cannot read {e!r}")

    def target(t, at: str, defined: set[str], new: bool) -> set[str]:
        if t[0] == "tuple":
            out: set[str] = set()
            for x in t[1]:
                out |= target(x, at, defined, new)
            return out
        if t[0] == "name":
            if not new and t[1] not in defined:
                fail(at, f"set {t[1]} before let")
            return {t[1]} - {"_"}               # a dropped value: nothing reads it
        if new:
            fail(at, "let binds a local name")
        place(t, at, defined, write=True)
        return set()

    def block(stmts: list, defined: set[str]) -> set[str] | None:
        """The names defined after the block, or None when control cannot
        run past it."""
        for s in stmts:
            defined = statement(s, defined)
            if defined is None:
                return None
        return defined

    def joined(outs: list) -> set[str] | None:
        live = [d for d in outs if d is not None]
        return set.intersection(*live) if live else None

    def statement(s, defined: set[str]) -> set[str] | None:
        op, at = s[0], s[-1]
        if op in ("let", "set"):
            expr(s[2], at, defined)
            return defined | target(s[1], at, defined, new=op == "let")
        if op == "if":
            outs = []
            for c, body in s[1]:
                expr(c, at, defined)
                outs.append(block(body, set(defined)))
            outs.append(block(s[2], set(defined)))
            return joined(outs)
        if op == "loop":
            expr(s[1], at, defined)
            block(s[2], set(defined))
            return defined
        if op == "for":
            expr(s[2], at, defined)
            expr(s[3], at, defined)
            block(s[4], defined | {s[1]})
            return defined
        if op in ("break", "continue", "stop", "unreachable", "return"):
            return None
        if op == "wait":
            return defined
        if op == "emit":
            rec = prog.records.get(s[1])
            if rec is None or not rec.stream:
                fail(at, f"{s[1]} is no stream")
            if len(s[2]) != len(rec.fields):
                fail(at, f"{s[1]} takes {len(rec.fields)} values")
            if r.kind == "processor" and s[1] not in r.writes:
                fail(at, f"{r.name} does not declare writes: {s[1]}")
            for a in s[2]:
                expr(a, at, defined)
            return defined
        if op == "run":
            callee = prog.routines.get(s[1])
            if callee is None:
                fail(at, f"{s[1]} is no routine")
            if len(s[2]) != len(callee.params):
                fail(at, f"{s[1]} takes {len(callee.params)} arguments")
            for a in s[2]:
                expr(a, at, defined)
            return defined
        if op == "match":
            expr(s[1], at, defined)
            enums = {prog.member(m) for m in s[2]}
            if len(enums) != 1 or None in enums:
                fail(at, f"a match's arms are members of one enum: {sorted(s[2])}")
            if not any(set(ms) == set(s[2]) for ms in prog.enums.values()):
                fail(at, f"a match has an arm for each member of its enum: {sorted(s[2])}")
            return joined([block(body, set(defined)) for body in s[2].values()])
        if op == "jump":
            if s[1][0] != "index":
                fail(at, "code is a slot of a collection")
            place(s[1], at, defined, write=False)
            expr(s[2], at, defined)
            return defined
        fail(at, f"unknown statement {op}")

    counts = set(r.params) | {s[1] for s in walk_statements(r.body) if s[0] == "for"}
    for c in r.requires:
        expr(c, where, set(r.params))
    block(r.body, set(r.params))


def names_read(tree) -> set[str]:
    """Every name a routine's text reads: each name but the locals a let or
    set binds."""
    if isinstance(tree, tuple) and tree[:1] in (("let",), ("set",)) and isinstance(tree[-1], str):
        targets = tree[1][1] if tree[1][0] == "tuple" else [tree[1]]
        return names_read([t for t in targets if t[0] != "name"]) | names_read(tree[2])
    if isinstance(tree, tuple) and len(tree) == 2 and tree[0] == "name" and isinstance(tree[1], str):
        return {tree[1]}
    items = tree.values() if isinstance(tree, dict) else tree if isinstance(tree, (list, tuple)) else ()
    return set().union(*map(names_read, items))


def check_unread(r: Routine) -> None:
    """A parameter or a local the routine never reads says nothing: every
    edit of what it is passed or set to is the same game. The half of a pair
    a routine drops is named _, which nothing reads."""
    read = names_read(r.body) | names_read(r.requires)
    for p in r.params:
        if p not in read:
            raise RunsError(f"{r.name}: its parameter {p} is never read")
    for s in walk_statements(r.body):
        if s[0] == "let":
            for t in s[1][1] if s[1][0] == "tuple" else [s[1]]:
                if t[0] == "name" and t[1] != "_" and t[1] not in read:
                    raise RunsError(f"{s[-1]}: the local {t[1]} is never read")


def constant_tables(prog: Program) -> set[tuple[str, str]]:
    """The collection fields that are tables of constants: no routine sets
    them, every slot's initial value is a number, and every mention names
    its slot by number or by a parameter of its routine (which a run passes
    as a number). Each mention is its slot's value, as a macro's arguments
    are in each expansion, and the table has no word of its own."""
    out = {(r.name, f) for r in prog.records.values() if r.count
           for f, (_, init) in r.fields.items()
           if init is not None and init[0] == "slots" and all(v[0] == "num" for v in init[1])}

    def go(x, params):
        if isinstance(x, list):
            for y in x:
                go(y, params)
        elif isinstance(x, tuple) and x:
            if x[0] == "index" and len(x) >= 3 and x[1][0] == "field" \
                    and (x[2][0] == "num" or x[2][0] == "name" and x[2][1] in params):
                return
            if x[0] == "field" and len(x) == 3 and x[1][0] == "name":
                out.discard((x[1][1], x[2]))
            for y in x:
                go(y, params)

    for r in prog.routines.values():
        for s in walk_statements(r.body):
            if s[0] in ("let", "set"):
                for t in s[1][1] if s[1][0] == "tuple" else [s[1]]:
                    if t[0] == "index" and t[1][0] == "field" and t[1][1][0] == "name":
                        out.discard((t[1][1][1], t[1][2]))
        go(r.body, set(r.params))
    return out


def walk_statements(stmts: list):
    for s in stmts:
        yield s
        if s[0] == "if":
            for _, body in s[1]:
                yield from walk_statements(body)
            yield from walk_statements(s[2])
        elif s[0] in ("loop", "for"):
            yield from walk_statements(s[-2])
        elif s[0] == "match":
            for body in s[2].values():
                yield from walk_statements(body)


def expr_touches(e, prog: Program, read: set[str]) -> None:
    """The Records an expression reads. Building an instruction reads only
    its operand's slot expression: the word it names is not read until the
    instruction runs."""
    op = e[0]
    if op in ("field", "index"):
        base = e[1] if op == "index" else e
        if base[0] == "field" and base[1][0] == "name" and base[1][1] in prog.records:
            read.add(base[1][1])
        if op == "index":
            expr_touches(e[2], prog, read)
    elif op == "call" and instruction_call(e[1], e[2]):
        if e[2] and e[2][0][0] == "index":
            expr_touches(e[2][0][2], prog, read)
    elif op == "call":
        for a in e[2]:
            expr_touches(a, prog, read)
    elif op in ("neg", "not"):
        expr_touches(e[1], prog, read)
    elif op == "bin":
        expr_touches(e[2], prog, read)
        expr_touches(e[3], prog, read)
    elif op == "tuple":
        for x in e[1]:
            expr_touches(x, prog, read)


def code_touches(prog: Program) -> tuple[set[str], set[str]]:
    """What code a `jump` runs may read and write: the operands of every
    instruction the program's text builds, and the display `dpy` plots on."""
    read: set[str] = set()
    written: set[str] = set()

    def visit(tree):
        if isinstance(tree, tuple) and tree[:1] == ("call",) and instruction_call(tree[1], tree[2]):
            x = tree[2][0] if tree[2] else None
            base = x[1] if x is not None and x[0] == "index" else x
            if OPERANDS[tree[1]] == "place" and base[0] == "field" and base[1][0] == "name":
                (written if tree[1] in ("dac", "dio") else read).add(base[1][1])
        elif tree == ("name", "dpy") and "dpy" in prog.instructions:
            written.add(prog.display)
        if isinstance(tree, (list, tuple)):
            for t in tree:
                visit(t)
        elif isinstance(tree, dict):
            visit(list(tree.values()))
    visit([r.body for r in prog.routines.values()])
    visit([e for rec in prog.records.values() for _, e in rec.fields.values()])
    return read, written


def touches(prog: Program, r: Routine) -> tuple[set[str], set[str]]:
    """The Records a routine's text reads and writes. A `jump` reads the
    code's Record and may touch whatever the code's instructions name."""
    read: set[str] = set()
    written: set[str] = set()

    def block(stmts: list):
        for s in stmts:
            op = s[0]
            if op in ("let", "set"):
                expr_touches(s[2], prog, read)
                for t in s[1][1] if s[1][0] == "tuple" else [s[1]]:
                    if t[0] == "index":
                        expr_touches(t[2], prog, read)
                        t = t[1]
                    if t[0] == "field":
                        written.add(t[1][1])
            elif op == "if":
                for c, body in s[1]:
                    expr_touches(c, prog, read)
                    block(body)
                block(s[2])
            elif op == "loop":
                expr_touches(s[1], prog, read)
                block(s[2])
            elif op == "for":
                expr_touches(s[2], prog, read)
                expr_touches(s[3], prog, read)
                block(s[4])
            elif op == "emit":
                written.add(s[1])
                for a in s[2]:
                    expr_touches(a, prog, read)
            elif op == "run":
                for a in s[2]:
                    expr_touches(a, prog, read)
            elif op == "match":
                expr_touches(s[1], prog, read)
                for body in s[2].values():
                    block(body)
            elif op == "jump":
                expr_touches(s[1], prog, read)
                expr_touches(s[2], prog, read)
                code_read, code_written = code_touches(prog)
                read.update(code_read)
                written.update(code_written)
    for c in r.requires:
        expr_touches(c, prog, read)
    block(r.body)
    return read, written


def check_declarations(prog: Program, r: Routine) -> None:
    """A Processor's contract is what its text does, in both directions:
    it declares every Record it reads (reads:) or writes (writes:, which lets
    it read the Record too), once, and each Record it declares is used."""
    read, written = touches(prog, r)
    if twice := sorted(r.reads & r.writes):
        raise RunsError(f"{r.name} declares {twice} under reads: and writes:; writes: lets it read them")
    for rec in sorted(written - r.writes):
        raise RunsError(f"{r.name} writes {rec}; declare writes: {rec}")
    for rec in sorted(read - r.reads - r.writes):
        raise RunsError(f"{r.name} reads {rec}; declare reads: {rec}")
    for rec in sorted(r.reads - read):
        raise RunsError(f"{r.name} declares reads: {rec}, but nothing in it reads {rec}")
    for rec in sorted(r.writes - written):
        raise RunsError(f"{r.name} declares writes: {rec}, but nothing in it writes {rec}")


NUMBER, BOOL, INSN = "number", "bool", "insn"
PAIR = ("pair", NUMBER, NUMBER)


def check_types(prog: Program) -> None:
    """What each expression computes, checked before anything runs, so that
    a value of the wrong kind is an error of the text and not of a run: a
    number (a word or a count; which one is the evaluator's check of the
    value), a condition, an instruction, a member of an enum, or a pair.
    A member's type is the enums that have a member of its name. A local
    takes the type of its let; a parameter, of what every run passes it."""
    params: dict[tuple[str, str], object] = {}

    def fits(want, got) -> bool:
        if want is None or got is None:
            return True
        if isinstance(want, frozenset) and isinstance(got, frozenset):
            return bool(want & got)
        return want == got

    def field_type(rec: str, fld: str):
        typ = prog.records[rec].fields[fld][0]
        return frozenset({typ}) if typ in prog.enums else INSN if typ == INSN else NUMBER

    def routine(r: Routine, passes: dict) -> None:
        local: dict[str, object] = {p: params.get((r.name, p)) for p in r.params}

        def fail(at: str, what: str):
            raise RunsError(f"{at}: {what}")

        def want(at: str, typ, e, what: str):
            got = expr(e, at)
            if not fits(typ, got):
                fail(at, f"{what} takes {name_of(typ)}, not {name_of(got)}: {e!r}")
            return got

        def expr(e, at: str):
            op = e[0]
            if op == "num":
                return NUMBER
            if op == "bool":
                return BOOL
            if op == "name":
                if e[1] in local:
                    return local[e[1]]
                if members := frozenset(n for n, ms in prog.enums.items() if e[1] in ms):
                    return members
                return INSN                         # an instruction with no operand (check_scope)
            if op in ("field", "index"):
                base = e[1] if op == "index" else e
                if op == "index":
                    want(at, NUMBER, e[2], "a slot")
                return field_type(base[1][1], base[2])
            if op == "call" and instruction_call(e[1], e[2]):
                if e[2] and e[2][0][0] == "index":
                    want(at, NUMBER, e[2][0][2], "a slot")
                return INSN
            if op == "call":
                for a in e[2]:
                    want(at, NUMBER, a, e[1])
                return NUMBER if e[1] in ("ral", "rar", "popcount") else PAIR
            if op == "neg":
                return want(at, NUMBER, e[1], "-")
            if op == "not":
                return want(at, BOOL, e[1], "not")
            if op == "tuple":
                return ("pair", *(expr(x, at) for x in e[1]))
            _, o, a, b = e
            if o in ("and", "or"):
                want(at, BOOL, a, o)
                want(at, BOOL, b, o)
                return BOOL
            left = expr(a, at)
            if left is None:
                expr(b, at)
                return BOOL if o in ("==", "!=", "<", "<=", ">", ">=") else NUMBER
            if o in ("==", "!=", "<", "<=", ">", ">=") and all(
                    x[0] == "num" or x[0] == "name" and x[1] not in local for x in (a, b)):
                fail(at, f"{o} of two constants is constant: {e!r}")
            if o in ("==", "!=") and isinstance(left, frozenset):
                want(at, left, b, o)
                return BOOL
            if left is not None and left != NUMBER:
                fail(at, f"{o} takes numbers, not {name_of(left)}: {a!r}")
            want(at, NUMBER, b, o)
            return BOOL if o in ("==", "!=", "<", "<=", ">", ">=") else NUMBER

        def store(t, got, at: str, new: bool):
            if t[0] == "tuple":
                if not (isinstance(got, tuple) and got[:1] == ("pair",) and len(got) == len(t[1]) + 1):
                    fail(at, f"cannot spread {name_of(got)} over {len(t[1])} names")
                for x, g in zip(t[1], got[1:]):
                    store(x, g, at, new)
                return
            if t[0] == "name":
                if t[1] in local and not fits(local[t[1]], got):
                    fail(at, f"{t[1]} holds {name_of(local[t[1]])}, not {name_of(got)}")
                if new or local.get(t[1]) is None:
                    local[t[1]] = got
                return
            base = t[1] if t[0] == "index" else t
            if t[0] == "index":
                want(at, NUMBER, t[2], "a slot")
            typ = field_type(base[1][1], base[2])
            if not fits(typ, got):
                fail(at, f"{base[1][1]}.{base[2]} holds {name_of(typ)}, not {name_of(got)}")

        def block(stmts: list):
            for s in stmts:
                op, at = s[0], s[-1]
                if op in ("let", "set"):
                    store(s[1], expr(s[2], at), at, new=op == "let")
                elif op == "if":
                    for c, body in s[1]:
                        want(at, BOOL, c, "a guard")
                        block(body)
                    block(s[2])
                elif op == "loop":
                    want(at, NUMBER, s[1], "a loop's bound")
                    block(s[2])
                elif op == "for":
                    want(at, NUMBER, s[2], "a counted loop")
                    want(at, NUMBER, s[3], "a counted loop")
                    local[s[1]] = NUMBER
                    block(s[4])
                elif op == "emit":
                    for a in s[2]:
                        want(at, NUMBER, a, s[1])
                elif op == "run":
                    for p, a in zip(prog.routines[s[1]].params, s[2]):
                        passes.setdefault((s[1], p), []).append((expr(a, at), at))
                elif op == "match":
                    got = expr(s[1], at)
                    arms = frozenset(n for n, ms in prog.enums.items() if set(s[2]) <= set(ms))
                    if not fits(got, arms) or not isinstance(got, (frozenset, type(None))):
                        fail(at, f"a match on {name_of(got)} with arms {sorted(s[2])}")
                    for body in s[2].values():
                        block(body)
                elif op == "jump":
                    if expr(s[1], at) != INSN:
                        fail(at, "a jump goes to a word of code")
                    want(at, NUMBER, s[2], "a jump's bound")
        for c in r.requires:
            want(r.name, BOOL, c, "requires")
        block(r.body)

    for rec in prog.records.values():
        for fld, (typ, init) in rec.fields.items():
            values = [] if init is None else init[1] if init[0] == "slots" else [init]
            for v in values:
                got = check_initial(prog, v)
                if not (fits(field_type(rec.name, fld), got) or typ == INSN and got == NUMBER):
                    raise RunsError(f"{rec.name}.{fld} holds {name_of(field_type(rec.name, fld))}, "
                                    f"not {name_of(got)}: {v!r}")
    while True:
        passes: dict = {}
        for r in prog.routines.values():
            routine(r, passes)
        found = {}
        for key, given in passes.items():
            types = {g for g, _ in given if g is not None}
            if len(types) > 1 and not (all(isinstance(t, frozenset) for t in types)
                                       and frozenset.intersection(*types)):
                raise RunsError(f"{given[0][1]}: {key[0]}'s {key[1]} is passed {sorted(map(name_of, types))}")
            if types:
                found[key] = frozenset.intersection(*types) if all(isinstance(t, frozenset) for t in types) \
                    else types.pop()
        if found == params:
            return
        params = found


def check_initial(prog: Program, e):
    """The type of an initial value: an expression of numbers, a member or
    an instruction, which touches no Record."""
    if e[0] == "name" and (members := frozenset(n for n, ms in prog.enums.items() if e[1] in ms)):
        return members
    if e[0] == "name" or e[0] == "call" and instruction_call(e[1], e[2]):
        return INSN
    return NUMBER


def name_of(typ) -> str:
    if typ is None:
        return "anything"
    if isinstance(typ, frozenset):
        return " or ".join(sorted(typ))
    if isinstance(typ, tuple):
        return "a pair"
    return {NUMBER: "a number", BOOL: "a condition", INSN: "an instruction"}[typ]


def check(prog: Program, sides: bool = True) -> Program:
    """Everything the evaluator checks before anything runs: what each kind
    may say, the names each routine uses, the types of what it computes, and
    the contracts."""
    declared_instructions.clear()
    declared_instructions.update(prog.instructions)
    for r in prog.routines.values():
        shape(r.body, r, in_loop=False)
        check_scope(prog, r)
        check_unread(r)
        if r.kind == "processor":
            check_declarations(prog, r)
        if any(r.name in fires(prog, t, set()) for t in runs_of(r.body)):
            raise RunsError(f"{r.name} fires itself: a recursion is a stack Record and a bounded Network loop")
    check_types(prog)
    check_contracts(prog)
    if sides:
        check_sides(prog)
    for rec in prog.records.values():
        for fld, (_, init) in rec.fields.items():
            if init is not None and init[0] == "slots" and len(init[1]) != rec.count:
                raise RunsError(f"{rec.name}.{fld}: {len(init[1])} initial values for {rec.count} slots")
    Machine(prog)                               # every initial value is a value of its field
    return prog


def program(root: Path) -> Program:
    return check(load(sorted(root.glob("*.runs")) + sorted(root.glob("*.runs-prim"))))
