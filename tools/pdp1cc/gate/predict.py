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
       Exactly one word changes, and it encodes c + 1 where it encoded c,
       in the same form (data word, literal operand, or constant load,
       whose form may move between cla, law, law i and lac).
count  a shift or rotate count n becomes n + 1. The run of 9s chunks for n
       becomes the run for n + 1.

The predictions are written here from the rule tables, not computed by the
compiler's own lowering code."""
from __future__ import annotations

import copy
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterator

from pycparser import c_ast

from .. import dialect, front, ir
from ..cli import COMPILE_ERRORS, compile_ast

MASK = ir.WORD_MASK
LAW_MAX = 0o7777
COMMUTATIVE = {"+": "add", "&": "and", "|": "ior", "^": "xor"}
COMPARE = {"<", ">=", "==", "!=", "<=", ">"}
SHIFT = {"<<": "sal", ">>": "sar"}
COUNT_ARG = {"rcl": 2, "rcr": 2, "scl": 2, "scr": 2, "ral": 1, "rar": 1, "ril": 1, "rir": 1}
MAX_SHIFT = 35

Line = tuple[str, str]          # (label, instruction text)


# ------------------------------------------------------------ rule tables

def load_const(v: int) -> str:
    if v == 0:
        return "cla"
    if v <= LAW_MAX:
        return f"law {v:o}"
    if v ^ MASK <= LAW_MAX:
        return f"law i {v ^ MASK:o}"
    return f"lac ({v:o}"


def chunks(n: int) -> list[str]:
    return [f"{k}s" for k in [9] * (n // 9) + ([n % 9] if n % 9 else [])]


def value_of(instr: str) -> tuple[str, int] | None:
    """(form, value) of a word that encodes a constant, else None."""
    if instr == "cla":
        return "load", 0
    if instr.startswith("law i "):
        return "load", int(instr[6:], 8) ^ MASK
    if instr.startswith("law "):
        return "load", int(instr[4:], 8)
    if instr.startswith("lac ("):
        return "load", int(instr[5:], 8)
    if "(" in instr:
        head, _, num = instr.partition("(")
        return head, int(num, 8)
    if instr.isdigit():
        return "data", int(instr, 8)
    return None


# ---------------------------------------------------------- the C side

@dataclass
class Site:
    kind: str                   # swap | const | count
    index: int                  # position in walk order
    line: int
    describe: str
    rewrites: Callable[[list[Line]], list[Rewrite]]     # where one copy of the edit may land
    edit: Callable[[c_ast.Node], None]
    copies: int = 1             # an unrolled loop body is emitted this many times

    def predict(self, old: list[Line]) -> list[list[Line]]:
        """Every output the rules allow: `copies` successive rewrites applied."""
        found = sorted(self.rewrites(old), key=lambda r: r[0])
        outs = []
        for k in range(len(found) - self.copies + 1):
            chosen = found[k:k + self.copies]
            if any(a[1] > b[0] for a, b in zip(chosen, chosen[1:])):
                continue
            new, pos = [], 0
            for start, end, words in chosen:
                new += old[pos:start] + words
                pos = end
            outs.append(new + old[pos:])
        return outs


Rewrite = tuple[int, int, list[Line]]   # old[start:end] becomes these lines


def walk(node: c_ast.Node, ctx: dict) -> Iterator[tuple[c_ast.Node, c_ast.Node | None, str, dict]]:
    """(node, parent, field, context) in a fixed order."""
    for name, child in node.children():
        sub = dict(ctx)
        if isinstance(node, c_ast.FuncDef):
            sub["function"] = node.decl.name
        if isinstance(node, c_ast.For) and name in ("init", "cond", "next"):
            sub["for_header"] = True
        if isinstance(node, c_ast.FuncCall) and name == "args":
            sub["call_node"] = node
        if isinstance(node, c_ast.For) and name == "stmt" and isinstance(node.cond, c_ast.BinaryOp):
            sub["copies"] = ctx.get("copies", 1) * dialect.c_int(node.cond.right)
        yield child, node, name, sub
        yield from walk(child, sub)


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
        self.locals: dict[str, set[str]] = {}
        for ext in ast.ext:
            if isinstance(ext, c_ast.FuncDef):
                names = {d.name for d, *_ in walk(ext.body, {}) if isinstance(d, c_ast.Decl)}
                self.locals[ext.decl.name] = names

    def memory_symbol(self, node: c_ast.Node, function: str) -> str | None:
        if not isinstance(node, c_ast.ID) or node.name in self.locals.get(function, ()):
            return None
        sig = self.unit.signatures.get(function)
        if sig is not None and any(p.name == node.name for p in sig.params):
            entry = next((p for p in sig.params if p.kind == "ac"), None)
            return sig.sym if sig.conv == "jda" and entry and entry.name == node.name else None
        storage = self.unit.objects.get(node.name)
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
    out: list[Site] = []
    for index, (node, parent, field, ctx) in enumerate(walk(ast, {})):
        if not own(node):
            continue
        fn = ctx.get("function")
        if isinstance(node, c_ast.BinaryOp) and node.op in COMMUTATIVE and fn:
            parts = [(leaves.load(x, fn), leaves.operand(x, fn)) for x in (node.left, node.right)]
            if all(load and opnd for load, opnd in parts):
                out.append(replace(swap_site(index, node, parts), copies=ctx.get('copies', 1)))
        token = int_token(node)
        if token is None or ctx.get("for_header"):
            continue
        if isinstance(parent, c_ast.BinaryOp) and field == "right" and parent.op in COMPARE:
            continue
        if isinstance(parent, c_ast.BinaryOp) and field == "right" and parent.op in SHIFT:
            if token + 1 <= MAX_SHIFT:
                out.append(replace(count_site(index, node, SHIFT[parent.op], token), copies=ctx.get('copies', 1)))
            continue
        builtin = builtin_count(parent, field, ctx)
        if builtin:
            if token + 1 <= MAX_SHIFT:
                out.append(replace(count_site(index, node, builtin, token), copies=ctx.get('copies', 1)))
            continue
        negated = isinstance(parent, c_ast.UnaryOp) and parent.op == "-"
        old = dialect.to_word(-token if negated else token, node)
        if old == 0 or token + 1 > MASK >> 1:
            continue
        new = dialect.to_word(-(token + 1) if negated else token + 1, node)
        out.append(replace(const_site(index, node, old, new), copies=ctx.get('copies', 1)))
    return out


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
            form = got[0]
            if form == "load":
                candidates = {load_const(new_v)}
                if instr.startswith("lac ("):       # a by-name literal keeps its form
                    candidates.add(f"lac ({new_v:o}")
            elif form == "data":
                candidates = {f"{new_v:o}"}
            else:
                candidates = {f"{form}({new_v:o}"}
            outs += [(i, i + 1, [(lab, c)]) for c in candidates]
        return outs

    def edit(n: c_ast.Constant) -> None:
        n.value = oct(dialect.c_int(n) + 1).replace("0o", "0")

    return Site("const", index, node.coord.line,
                f"constant {old_v:06o} -> {new_v:06o}", rewrites, edit)


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

    return Site("count", index, node.coord.line, f"{mnemonic} count {n} -> {n + 1}", rewrites, edit)


# -------------------------------------------------------------- running

def lines_of(text: str) -> list[Line]:
    out = []
    for raw in text.splitlines():
        label, _, instr = raw.partition("\t")
        out.append((label.rstrip(","), instr.strip()))
    return out


def node_at(ast: c_ast.FileAST, index: int) -> c_ast.Node:
    for i, (node, *_rest) in enumerate(walk(ast, {})):
        if i == index:
            return node
    raise IndexError(index)


def check_file(path: Path) -> tuple[Counter, list[str]]:
    ast = front.parse(path)
    old = lines_of(compile_ast(copy.deepcopy(ast), trace=False))
    unit = dialect.lower_unit(copy.deepcopy(ast))
    tested, failures = Counter(), []
    for site in sites(ast, unit):
        edited = copy.deepcopy(ast)
        site.edit(node_at(edited, site.index))
        try:
            new = lines_of(compile_ast(edited, trace=False))
        except COMPILE_ERRORS as e:
            failures.append(f"{path.name}:{site.line}: {site.describe}: compile error {e}")
            continue
        tested[site.kind] += 1
        if new not in site.predict(old):
            failures.append(f"{path.name}:{site.line}: {site.describe}: output differs from the prediction"
                            + ("" if new != old else " (output unchanged)"))
    return tested, failures


def gate(files: list[Path]) -> int:
    failed = 0
    for f in files:
        tested, failures = check_file(f)
        total = sum(tested.values())
        status = "ok" if not failures else f"{len(failures)} WRONG"
        kinds = " ".join(f"{k} {tested[k]}" for k in ("swap", "const", "count"))
        print(f"  {f.name:<16} {total:>3} edits ({kinds})  {status}")
        for line in failures[:8]:
            print("    " + line)
        failed |= bool(failures)
    return 1 if failed else 0
