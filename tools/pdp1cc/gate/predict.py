"""G6: prediction edits. Each edit is derived mechanically from a file's C
AST, and the lowering rules say beforehand which words it changes. The gate
compiles the edited AST and requires the Macro text to equal the original
with exactly the predicted rewrite. A compiler that replays memorized words
changes nothing, or changes the wrong words, and fails.

Edits, applied one at a time to every candidate in the file:

swap   `l op r` with op in + & | ^ and both operands memory words or
       constants becomes `r op l`. Operand order is instruction order, so
       the words [load l] [op r] become [load r] [op l]. A load is absent
       when the value is already in AC (TRACK).
const  a constant c used as a value becomes c + 1 (-c becomes -(c + 1)).
       Exactly one line changes, and it encodes c + 1 where it encoded c,
       in the same form (data word, literal operand, origin, reserved
       length, or constant load, whose form may move between cla, law,
       law i and lac).
count  a shift or rotate count n becomes n + 1. The run of 9s chunks for n
       becomes the run for n + 1 (sal/sar, or sil/sir for a value in IO).
       In an XCT function a run that would grow past one word is predicted
       to be refused.
flag   a program flag n (stf, clf, flag, I_STF, I_CLF, I_SZF) becomes n + 1:
       the one instruction or literal that names flag n names n + 1. Past
       flag 7 (flag 6 for a test) it is refused. An I_RCL-style count n
       becomes n + 1 in its literal (`rcl 3s` -> `rcl 4s`, and the bare
       `scl` of count 0 -> `scl 1s`), refused past 9.
       A sense switch n (`szs n0`) and a dpy intensity n (`dpy-i+n00`) are
       fields too, refused past 6 and 7.

The flags c of `f | (word)c`, a function's address with flags above it,
become c + 1, which sets an address bit: the edit is predicted refused.

A constant inside a constant expression (`8192 - 1537`, `0400 - 010`)
changes the expression's value: the prediction is the const rewrite of the
folded value, worked out here by C's rules. An array offset (`ring + 8`)
changes the offset its address operand names (`ring+10`). Case labels and
array lengths are not values: their edits are not made.

An edit in a static inline function, or in an unrolled loop, lands once in
each copy: the output must be the original with exactly that many of the
predicted rewrites applied, each in a different copy. A rewrite counts for
a copy when the word it rewrites was laid out in that copy (an inline
function's body at one call, an unrolled body in one iteration), so a
compiler that changes one copy twice, or a matching word outside the
copies, fails. A count edit that lengthens a case of Duff's
device (a switch on a HOMED word) is predicted to be refused: those cases
are one power of two of words each.

The predictions are written here from the rule tables, not computed by the
compiler's own lowering code."""
from __future__ import annotations

import copy
import re
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterator

from pycparser import c_ast

from .. import dialect, emit, front, ir
from ..cli import COMPILE_ERRORS, lay_out

MASK = ir.WORD_MASK
LAW_MAX = 0o7777
COMMUTATIVE = {"+": "add", "&": "and", "|": "ior", "^": "xor"}
COMPARE = {"<", ">=", "==", "!=", "<=", ">"}
SHIFT = {"<<": "sal", ">>": "sar"}
IO_SHIFT = {"<<": "sil", ">>": "sir"}
COUNT_ARG = {"rcl": 2, "rcr": 2, "scl": 2, "scr": 2, "ral": 1, "rar": 1, "ril": 1, "rir": 1}
MAX_SHIFT = 35
# A builtin whose argument is a field of one instruction: its mnemonic,
# whether the field is a shift count, the largest value, and the error past it.
FIELD_ARG = {"stf": ("stf", False, 7), "clf": ("clf", False, 7), "flag": ("szf", False, 6),
             "I_STF": ("stf", False, 7), "I_CLF": ("clf", False, 7), "I_SZF": ("szf", False, 7),
             "I_RCL": ("rcl", True, 9), "I_RAL": ("ral", True, 9), "I_SCL": ("scl", True, 9),
             "I_SCR": ("scr", True, 9), "I_SAR": ("sar", True, 9),
             "sense": ("szs", False, 6), "dpy": ("dpy", False, 7)}
FIELD_POSITION = {"dpy": "exprs[2]"}
FIELD_ERROR = {"szs": "sense switch", "dpy": "intensity"}
FOLD = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b,
        "<<": lambda a, b: a << b, ">>": lambda a, b: a >> b}

Line = tuple[str, str]          # (label, instruction text)
LineCopies = dict[ir.Construct, str]


# ------------------------------------------------------------ rule tables

def load_const(v: int) -> str:
    if v == 0:
        return "cla"
    if v == MASK:
        return "clc"
    if v <= LAW_MAX:
        return f"law {v:o}"
    if v ^ MASK <= LAW_MAX:
        return f"law i {v ^ MASK:o}"
    return f"lac ({v:o}"


def chunks(n: int) -> list[str]:
    return [f"{k}s" for k in [9] * (n // 9) + ([n % 9] if n % 9 else [])]


OCTAL = r"([0-7]+)"
FORMS = [(re.compile(r"cla$"), "load", lambda m: 0),
         (re.compile(r"clc$"), "load", lambda m: MASK),
         (re.compile(r"law i " + OCTAL + "$"), "load", lambda m: int(m.group(1), 8) ^ MASK),
         (re.compile(r"law " + OCTAL + "$"), "load", lambda m: int(m.group(1), 8)),
         (re.compile(r"lac \(" + OCTAL + "$"), "load", lambda m: int(m.group(1), 8)),
         (re.compile(r"(\w+ )\(" + OCTAL + "$"), None, lambda m: int(m.group(2), 8)),
         (re.compile(OCTAL + "$"), "data", lambda m: int(m.group(1), 8)),
         (re.compile(OCTAL + "/$"), "origin", lambda m: int(m.group(1), 8)),
         (re.compile(r"\. " + OCTAL + "/$"), "reserve", lambda m: int(m.group(1), 8))]


def value_of(instr: str) -> tuple[str, int] | None:
    """(form, value) of a line that encodes a constant, else None."""
    for pattern, form, value in FORMS:
        if m := pattern.match(instr):
            return (form or m.group(1) + "("), value(m)
    return None


def encode(form: str, v: int) -> str:
    return {"load": load_const(v), "data": f"{v:o}", "origin": f"{v:o}/",
            "reserve": f". {v:o}/"}.get(form, f"{form}{v:o}")


# ---------------------------------------------------------- the C side

@dataclass
class Site:
    kind: str                   # swap | const | count
    index: int                  # position in walk order
    line: int
    describe: str
    rewrites: Callable[[list[Line]], list[Rewrite]]     # where one copy of the edit may land
    edit: Callable[[c_ast.Node], None]
    copies: int = 1
    replicas: tuple[ir.Construct, ...] = ()
    error: str | None = None    # the edit must be refused with this message instead
    n: int = 0                  # a count site's count

    def copy_at(self, copies_of: LineCopies) -> tuple[str, ...] | None:
        if any(r not in copies_of for r in self.replicas):
            return None
        return tuple(copies_of[r] for r in self.replicas)

    def matches(self, old: list[Line], new: list[Line], copies_of: list[LineCopies]) -> bool:
        at: dict[int, list[tuple[int, list[Line]]]] = {}
        for start, end, words in self.rewrites(old):
            if old[start:end] != words:
                at.setdefault(start, []).append((end, words))
        todo, seen = [(0, 0, frozenset())], set()
        while todo:
            state = todo.pop()
            if state in seen:
                continue
            seen.add(state)
            i, j, done = state
            if i == len(old) and j == len(new) and len(done) == self.copies:
                return True
            if i < len(old) and j < len(new) and old[i] == new[j]:
                todo.append((i + 1, j + 1, done))
            copy = self.copy_at(copies_of[i]) if i in at and len(done) < self.copies else None
            if copy is not None and copy not in done:
                for end, words in at[i]:
                    if new[j:j + len(words)] == words:
                        todo.append((end, j + len(words), done | {copy}))
        return False


Rewrite = tuple[int, int, list[Line]]   # old[start:end] becomes these lines


def walk(node: c_ast.Node, ctx: dict) -> Iterator[tuple[c_ast.Node, c_ast.Node | None, str, dict]]:
    for name, child in node.children():
        sub = dict(ctx)
        sub["ancestors"] = ctx.get("ancestors", ()) + ((node, name),)
        if isinstance(node, c_ast.FuncDef):
            sub["function"] = node.decl.name
            sub["copies"] = ctx.get("inline_copies", {}).get(node.decl.name, 1)
            inline = node.decl.name in ctx.get("inline_copies", {})
            sub["replicas"] = (ir.InlineBody(node.decl.name),) if inline else ()
        if isinstance(node, c_ast.Switch) and _homed_switch(node, ctx) and \
                isinstance(child, c_ast.Compound):
            sub["duff_cases"] = child.block_items[:-1] if child.block_items else []
        if isinstance(node, c_ast.Compound) and child in ctx.get("duff_cases", ()):
            sub["in_duff_case"] = True
        if isinstance(node, c_ast.For) and name in ("init", "cond", "next"):
            sub["for_header"] = True
        if isinstance(node, c_ast.FuncCall) and name == "args":
            sub["call_node"] = node
        if isinstance(node, c_ast.For) and name == "stmt" and isinstance(node.cond, c_ast.BinaryOp):
            sub["copies"] = ctx.get("copies", 1) * dialect.c_int(node.cond.right)
            sub["replicas"] = ctx.get("replicas", ()) + (ir.UnrolledBody(str(node.coord)),)
        yield child, node, name, sub
        yield from walk(child, sub)


def _homed_switch(node: c_ast.Switch, ctx: dict) -> bool:
    cond = node.cond
    return isinstance(cond, c_ast.Cast) and isinstance(cond.expr, c_ast.ID) and \
        cond.expr.name in ctx.get("homed", set())


def fold(node: c_ast.Node, bump: c_ast.Node | None = None) -> int | None:
    if isinstance(node, c_ast.Constant) and node.type == "int":
        return dialect.c_int(node) + (node is bump)
    if isinstance(node, c_ast.UnaryOp) and node.op == "-":
        v = fold(node.expr, bump)
        return None if v is None else -v
    if isinstance(node, c_ast.BinaryOp) and node.op in FOLD:
        a, b = fold(node.left, bump), fold(node.right, bump)
        return None if a is None or b is None else FOLD[node.op](a, b)
    return None


def ones_complement(v: int) -> int:
    return v if v >= 0 else (-v) ^ MASK


def folded_top(ancestors) -> tuple[c_ast.Node | None, c_ast.Node | None, str]:
    top, i = None, len(ancestors) - 1
    while i >= 0:
        node, _ = ancestors[i]
        if isinstance(node, (c_ast.BinaryOp, c_ast.UnaryOp)) and fold(node) is not None:
            top, i = node, i - 1
        else:
            break
    if top is None:
        return None, None, ""
    return top, ancestors[i][0] if i >= 0 else None, ancestors[i][1] if i >= 0 else ""


def inline_copies(ast: c_ast.FileAST, unit: ir.Unit) -> dict[str, int]:
    inlines = set(unit.inlines or {})
    copies = {name: 0 for name in inlines}
    for _ in range(len(inlines) + 1):
        new = {name: 0 for name in inlines}
        for node, _parent, _field, ctx in walk(ast, {"inline_copies": copies}):
            if isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID) \
                    and node.name.name in inlines:
                new[node.name.name] += ctx.get("copies", 1)
        if new == copies:
            break
        copies = new
    return copies


def own(node: c_ast.Node) -> bool:
    return node.coord is not None and not node.coord.file.endswith("pdp1.h")


def int_token(node: c_ast.Node) -> int | None:
    if isinstance(node, c_ast.Constant) and node.type == "int":
        return dialect.c_int(node)
    return None


class Leaves:
    """Macro text of a leaf operand, from the dialect's storage rules."""

    def __init__(self, unit: ir.Unit, ast: c_ast.FileAST):
        self.unit = unit
        self.arrays = {e.name for e in ast.ext
                       if isinstance(e, c_ast.Decl) and isinstance(e.type, c_ast.ArrayDecl)}
        self.locals: dict[str, set[str]] = {}
        self.registers: dict[str, set[str]] = {}
        for ext in ast.ext:
            if isinstance(ext, c_ast.FuncDef):
                decls = [d for d, *_ in walk(ext.body, {}) if isinstance(d, c_ast.Decl)]
                params = ext.decl.type.args.params if ext.decl.type.args else []
                self.locals[ext.decl.name] = {d.name for d in decls}
                self.registers[ext.decl.name] = {d.name for d in decls + list(params)
                                                 if "register" in getattr(d, "storage", [])}

    def in_io(self, node: c_ast.Node, function: str) -> bool:
        """A register local or the low half of a dword: a value in IO."""
        if isinstance(node, c_ast.StructRef) and node.type == "." and node.field.name == "lo":
            return True
        return isinstance(node, c_ast.ID) and node.name in self.registers.get(function, ())

    def memory_symbol(self, node: c_ast.Node, function: str) -> str | None:
        if not isinstance(node, c_ast.ID) or node.name in self.locals.get(function, ()) \
                or node.name in self.arrays:
            return None
        sig = self.unit.signatures.get(function)
        if sig is not None and any(p.name == node.name for p in sig.params):
            entry = next((p for p in sig.params if p.kind is ir.ParamKind.AC), None)
            return sig.sym if sig.conv is ir.Conv.JDA and entry and entry.name == node.name else None
        storage = self.unit.objects.get(node.name)
        if isinstance(storage, ir.Pool):
            return "\\" + storage.sym
        return storage.sym if isinstance(storage, ir.Memory) else None

    def constant(self, node: c_ast.Node) -> int | None:
        if (t := int_token(node)) is not None:
            return dialect.to_word(t, node)
        if isinstance(node, c_ast.UnaryOp) and node.op == "-" and (t := int_token(node.expr)) is not None:
            return dialect.to_word(-t, node)
        return None

    def load(self, node, function) -> str | None:
        if (v := self.constant(node)) is not None:
            return load_const(v)
        sym = self.memory_symbol(node, function)
        return f"lac {sym}" if sym else None

    def operand(self, node, function) -> str | None:
        if (v := self.constant(node)) is not None:
            return f"({v:o}"
        return self.memory_symbol(node, function)


def sites(ast: c_ast.FileAST, unit: ir.Unit) -> list[Site]:
    leaves = Leaves(unit, ast)
    homed = {name for name, s in unit.objects.items() if isinstance(s, ir.Homed)}
    top_ctx = {"inline_copies": inline_copies(ast, unit), "homed": homed}
    top_ctx["duff_inlines"] = {n.name.name for n, _p, _f, c in walk(ast, top_ctx)
                               if c.get("in_duff_case") and isinstance(n, c_ast.FuncCall)
                               and isinstance(n.name, c_ast.ID) and n.name.name in (unit.inlines or {})}
    out: list[Site] = []
    for index, (node, parent, field, ctx) in enumerate(walk(ast, top_ctx)):
        if not own(node):
            continue
        fn = ctx.get("function")

        def add(site: Site) -> None:
            out.append(replace(site, copies=ctx.get("copies", 1), replicas=ctx.get("replicas", ())))
        if isinstance(node, c_ast.BinaryOp) and node.op in COMMUTATIVE and fn and fold(node) is None:
            parts = [(leaves.load(x, fn), leaves.operand(x, fn)) for x in (node.left, node.right)]
            if all(load and opnd for load, opnd in parts):
                add(swap_site(index, node, parts))
        token = int_token(node)
        if token is None or ctx.get("for_header"):
            continue
        top, top_parent, top_field = folded_top(ctx.get("ancestors", ()))
        if top is not None:
            parent, field = top_parent, top_field
        if isinstance(parent, c_ast.BinaryOp) and field == "right" and parent.op in COMPARE:
            continue
        if isinstance(parent, (c_ast.Case, c_ast.ArrayDecl)):
            continue
        if code_flags(node, ctx, unit):
            old = dialect.to_word(token, node)
            add(replace(const_site(index, node, old, old + 1), error="flags must lie above"))
            continue
        if isinstance(parent, c_ast.BinaryOp) and parent.op == "+" and field == "right" and \
                isinstance(parent.left, c_ast.ID) and parent.left.name in leaves.arrays:
            expr = top if top is not None else node
            sym = unit.objects[parent.left.name].sym
            add(offset_site(index, node, sym, fold(expr), fold(expr, node)))
            continue
        if top is not None:
            if isinstance(parent, c_ast.BinaryOp) and field == "right" and parent.op in SHIFT:
                continue
            if field_arg(parent, ctx, field) is not None or builtin_count(parent, field, ctx):
                continue
            old, new = fold(top), fold(top, node)
            if ones_complement(old) == 0 or abs(new) > MASK >> 1:
                continue
            add(const_site(index, node, ones_complement(old), ones_complement(new)))
            continue
        if (fieldarg := field_arg(parent, ctx, field)) is not None:
            add(field_site(index, node, *fieldarg, token))
            continue
        if isinstance(parent, c_ast.BinaryOp) and field == "right" and parent.op in SHIFT:
            mnemonic = (IO_SHIFT if leaves.in_io(parent.left, fn) else SHIFT)[parent.op]
            if token + 1 <= MAX_SHIFT:
                add(refuse_lengthening(count_site(index, node, mnemonic, token), unit, fn, ctx))
            continue
        builtin = builtin_count(parent, field, ctx)
        if builtin:
            if token + 1 <= MAX_SHIFT:
                add(refuse_lengthening(count_site(index, node, builtin, token), unit, fn, ctx))
            continue
        negated = isinstance(parent, c_ast.UnaryOp) and parent.op == "-"
        old = dialect.to_word(-token if negated else token, node)
        if old == 0 or token + 1 > MASK >> 1:
            continue
        new = dialect.to_word(-(token + 1) if negated else token + 1, node)
        add(const_site(index, node, old, new))
    return out


def code_flags(node: c_ast.Node, ctx: dict, unit: ir.Unit) -> bool:
    """The constant c of `f | (word)c`, the flags above a function's
    address: c + 1 sets an address bit, which the rule refuses."""
    chain = [n for n, _ in ctx.get("ancestors", ())]
    return len(chain) >= 2 and isinstance(chain[-1], c_ast.Cast) and \
        isinstance(chain[-2], c_ast.BinaryOp) and chain[-2].op == "|" and \
        chain[-2].right is chain[-1] and isinstance(chain[-2].left, c_ast.ID) and \
        chain[-2].left.name in unit.signatures


def field_arg(parent, ctx: dict, field: str) -> tuple[str, bool, int] | None:
    call = ctx.get("call_node")
    if not isinstance(parent, c_ast.ExprList) or call is None or call.args is not parent:
        return None
    name = call.name.name if isinstance(call.name, c_ast.ID) else None
    if name in FIELD_POSITION and field != FIELD_POSITION[name]:
        return None
    return FIELD_ARG.get(name)


def field_text(mnemonic: str, shift: bool, n: int) -> tuple[str, str]:
    if mnemonic == "szs":
        return rf"\bszs( i)? {n << 3:o}\b", f"szs\\1 {(n + 1) << 3:o}"
    if mnemonic == "dpy":
        return (rf"^dpy-i\+{n << 6:o}$" if n else r"^dpy-i$"), f"dpy-i+{(n + 1) << 6:o}"
    if shift and n == 0:                # the empty shift is the bare mnemonic
        return rf"\b{mnemonic}( i)?$", f"{mnemonic}\\1 1s"
    unit = "s" if shift else ""
    return rf"\b{mnemonic}( i)? {n:o}{unit}\b", f"{mnemonic}\\1 {n + 1:o}{unit}"


def field_site(index: int, node: c_ast.Constant, mnemonic: str, shift: bool, largest: int,
               n: int) -> Site:
    old_t, new_t = field_text(mnemonic, shift, n)

    def rewrites(old: list[Line]) -> list[Rewrite]:
        return [(i, i + 1, [(lab, re.sub(old_t, new_t, instr, count=1))])
                for i, (lab, instr) in enumerate(old) if re.search(old_t, instr)]

    def edit(n_: c_ast.Constant) -> None:
        n_.value = str(n + 1)

    error = None
    if n + 1 > largest:
        error = "shifts 0..9 places" if shift else FIELD_ERROR.get(mnemonic, "flag")
    return Site("flag", index, node.coord.line, f"{mnemonic} field {n} -> {n + 1}", rewrites, edit,
                error=error)


def offset_site(index: int, node: c_ast.Constant, sym: str, old: int, new: int) -> Site:
    def text(k: int) -> str:
        return f"{sym}+{k:o}" if k else sym

    pattern = re.compile(rf"(?<![\w+]){re.escape(text(old))}(?![\w+])")

    def rewrites(old_lines: list[Line]) -> list[Rewrite]:
        return [(i, i + 1, [(lab, pattern.sub(text(new), instr, count=1))])
                for i, (lab, instr) in enumerate(old_lines) if pattern.search(instr)]

    def edit(n_: c_ast.Constant) -> None:
        n_.value = oct(dialect.c_int(n_) + 1).replace("0o", "0")

    return Site("const", index, node.coord.line, f"offset {sym}+{old:o} -> {sym}+{new:o}",
                rewrites, edit)


def builtin_count(parent, field: str, ctx: dict) -> str | None:
    call = ctx.get("call_node")
    if not isinstance(parent, c_ast.ExprList) or call is None or call.args is not parent:
        return None
    name = call.name.name if isinstance(call.name, c_ast.ID) else None
    if name in COUNT_ARG and field == f"exprs[{COUNT_ARG[name]}]":
        return name
    return None


def swap_site(index: int, node: c_ast.BinaryOp, parts) -> Site:
    (load_l, opnd_l), (load_r, opnd_r) = parts
    op = COMMUTATIVE[node.op]

    def rewrites(old: list[Line]) -> list[Rewrite]:
        outs = []
        for i, (_, instr) in enumerate(old):
            if instr != f"{op} {opnd_r}":
                continue
            starts = [i] + ([i - 1] if i > 0 and old[i - 1][1] == load_l and not old[i][0] else [])
            for a in starts:
                lab = old[a][0]
                for win in ([load_r, f"{op} {opnd_l}"], [f"{op} {opnd_l}"]):
                    outs.append((a, i + 1, [(lab, win[0])] + [("", w) for w in win[1:]]))
        return outs

    def edit(n: c_ast.BinaryOp) -> None:
        n.left, n.right = n.right, n.left

    return Site("swap", index, node.coord.line, f"swap operands of `{node.op}`", rewrites, edit)


def const_site(index: int, node: c_ast.Constant, old_v: int, new_v: int) -> Site:
    def rewrites(old: list[Line]) -> list[Rewrite]:
        outs = []
        for i, (lab, instr) in enumerate(old):
            got = value_of(instr)
            if got is None or got[1] != old_v:
                continue
            candidates = {encode(got[0], new_v)}
            if instr.startswith("lac ("):           # a by-name literal keeps its form
                candidates.add(f"lac ({new_v:o}")
            outs += [(i, i + 1, [(lab, c)]) for c in candidates]
        return outs

    def edit(n: c_ast.Constant) -> None:
        n.value = oct(dialect.c_int(n) + 1).replace("0o", "0")

    return Site("const", index, node.coord.line,
                f"constant {old_v:06o} -> {new_v:06o}", rewrites, edit)


def refuse_lengthening(site: Site, unit: ir.Unit, function: str | None, ctx: dict) -> Site:
    if site.kind != "count" or len(chunks(site.n + 1)) <= len(chunks(site.n)):
        return site
    sig = unit.signatures.get(function or "")
    if sig is not None and sig.conv is ir.Conv.XCT:
        return replace(site, error="must lower to exactly one word")
    if ctx.get("in_duff_case") or function in ctx.get("duff_inlines", ()):
        return replace(site, error="power of two of words")
    return site


def count_site(index: int, node: c_ast.Constant, mnemonic: str, n: int) -> Site:
    before = [f"{mnemonic} {c}" for c in chunks(n)]
    after = [f"{mnemonic} {c}" for c in chunks(n + 1)]

    def rewrites(old: list[Line]) -> list[Rewrite]:
        outs = []
        for i in range(len(old) - len(before) + 1):
            run = old[i:i + len(before)]
            if [w for _, w in run] == before and not any(lab for lab, _ in run[1:]):
                outs.append((i, i + len(before), [(run[0][0], after[0])] + [("", w) for w in after[1:]]))
        return outs

    def edit(n_: c_ast.Constant) -> None:
        n_.value = str(n + 1)

    return Site("count", index, node.coord.line, f"{mnemonic} count {n} -> {n + 1}", rewrites, edit, n=n)


# -------------------------------------------------------------- running

def lines_of(text: str) -> list[Line]:
    out = []
    for raw in text.splitlines():
        label, tab, instr = raw.partition("\t")
        out.append((label.rstrip(","), instr.strip()) if tab else ("", raw.strip()))
    return out


def compiled(ast: c_ast.FileAST) -> tuple[list[Line], list[LineCopies]]:
    words = lay_out(ast, "z")
    copies_of = [{c.construct: c.instance for c in getattr(w, "copies", ())} for w in words]
    lines = lines_of(emit.emit(words, trace=False))
    assert len(lines) == len(copies_of), "one line per laid-out item"
    return lines, copies_of


def node_at(ast: c_ast.FileAST, index: int) -> c_ast.Node:
    for i, (node, *_rest) in enumerate(walk(ast, {})):
        if i == index:
            return node
    raise IndexError(index)


@dataclass(frozen=True)
class Prepared:
    ast: c_ast.FileAST
    old: list[Line]
    copies_of: list[LineCopies]
    sites: list[Site]


_PREPARED: dict[Path, Prepared] = {}


def prepared(path: Path) -> Prepared:
    if path not in _PREPARED:
        ast = front.parse(path)
        old, copies_of = compiled(copy.deepcopy(ast))
        unit = dialect.lower_unit(copy.deepcopy(ast))
        _PREPARED[path] = Prepared(ast, old, copies_of, sites(ast, unit))
    return _PREPARED[path]


def check_site(path: Path, k: int) -> tuple[str, str | None]:
    p = prepared(path)
    site = p.sites[k]
    edited = copy.deepcopy(p.ast)
    site.edit(node_at(edited, site.index))
    at = f"{path.name}:{site.line}: {site.describe}"
    try:
        new, _ = compiled(edited)
    except COMPILE_ERRORS as e:
        if site.error is None or site.error not in str(e):
            return site.kind, f"{at}: compile error {e}"
        return site.kind, None
    if site.error is not None:
        return site.kind, f"{at}: compiled; predicted the error {site.error!r}"
    if not site.matches(p.old, new, p.copies_of):
        return site.kind, f"{at}: output differs from the prediction" + \
            ("" if new != p.old else " (output unchanged)")
    return site.kind, None


def check_file(path: Path, pool: ProcessPoolExecutor) -> tuple[Counter, list[str]]:
    n = len(prepared(path).sites)
    results = list(pool.map(check_site, [path] * n, range(n), chunksize=8))
    return Counter(kind for kind, _ in results), [f for _, f in results if f]


def gate(files: list[Path]) -> int:
    failed = 0
    with ProcessPoolExecutor() as pool:
        checked = [(f, *check_file(f, pool)) for f in files]
    for f, tested, failures in checked:
        total = sum(tested.values())
        status = "ok" if not failures else f"{len(failures)} WRONG"
        kinds = " ".join(f"{k} {tested[k]}" for k in ("swap", "const", "count", "flag"))
        print(f"  {f.name:<16} {total:>3} edits ({kinds})  {status}")
        for line in failures[:8]:
            print("    " + line)
        failed |= bool(failures)
    return 1 if failed else 0
