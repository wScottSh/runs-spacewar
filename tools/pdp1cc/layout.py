"""Orders a unit's items in C definition order (LAY-ORDER), attaches labels
to the word they name, and merges labels that land on the same cell."""
from __future__ import annotations

from dataclasses import replace

from . import inline, ir
from .dialect import Namer
from .rules import check
from .select import BIN_MNEMONIC, FunctionLowerer, W, _returns, _tail_calls, datum_words, preserves_io


class LayoutError(Exception):
    pass


def place(unit: ir.Unit, label_prefix: str) -> list[ir.Emitted]:
    namer = Namer(label_prefix, unit.next_label)
    items: list[ir.Item] = []
    entered_by_fallthrough = False
    keeps_io: dict[str, bool] = {}
    inlines = unit.inlines or {}
    homes = home_ops([t for t in unit.items if isinstance(t, ir.Function)] + list(inlines.values()))
    exits = exit_cells([t for t in unit.items if isinstance(t, ir.Function)])
    for n, top in enumerate(unit.items):
        if top.at is not None:
            items.append(ir.Origin(top.at, check("LAY-AT")))
        match top:
            case ir.RegionBreak():
                items.append(ir.Break())
            case ir.Function():
                after = unit.items[n + 1] if n + 1 < len(unit.items) else None
                following = after.sym if isinstance(after, (ir.Function, ir.Datum, ir.Space)) and \
                    after.at is None else None
                lowerer = FunctionLowerer(top, namer, following, keeps_io, inlines, homes, exits=exits)
                own = lowerer.lower()
                keeps_io[top.sym] = preserves_io(own) and not lowerer.fell_through
                if entered_by_fallthrough:
                    own = _tag_first_word(own, "LAY-FALLTHROUGH")
                entered_by_fallthrough = lowerer.fell_through
                items += own
            case ir.Datum():
                items += datum_words(top)
            case ir.Space():
                items += [ir.LabelDef(top.sym), ir.Reserve(top.size, check("ST-RESERVE"))]
    homeless = [name for name, s in unit.objects.items() if isinstance(s, ir.HomedInsn)
                and not any(isinstance(i, ir.LabelDef) and i.name == s.sym for i in items)]
    if homeless:
        raise LayoutError(f"HOMED insn {', '.join(homeless)} has no home: run it with xct(x, ...)")
    return attach_labels(items)


def exit_cells(functions: list[ir.Function]) -> dict[str, str]:
    """The exit cell each function returns through. One whose returns all
    tail-call one BLOCK defined here returns through that block's exit
    cell, so a function adopting it patches that cell (LAY-ADOPT)."""
    defined = {f.sig.name: f for f in functions}
    out: dict[str, str] = {}

    def resolve(f: ir.Function, seen: frozenset[str]) -> str:
        tails = _tail_calls(f.body)
        targets = {r.value.sig.name for r in tails}
        plain = [r for r in _returns(f.body) if r not in tails and not isinstance(r.value, ir.IndirectCall)]
        if plain or len(targets) != 1 or (target := targets.pop()) not in defined or target in seen:
            return f.sig.exit_sym
        return resolve(defined[target], seen | {f.sig.name})
    for f in functions:
        out[f.sig.name] = resolve(f, frozenset())
    return out


def home_ops(functions: list[ir.Function]) -> dict[str, str]:
    ops: dict[str, str] = {}
    for fn in functions:
        for n in inline.iter_nodes(fn.body):
            if isinstance(n, ir.Xct) and isinstance(n.insn, ir.HomeLoad):
                ops[n.insn.pointer.storage.sym] = "xct"
            elif isinstance(n, ir.Binary) and isinstance(n.right, ir.HomeLoad):
                ops[n.right.pointer.storage.sym] = BIN_MNEMONIC[n.op]
            elif isinstance(n, ir.HomeStore):
                io = isinstance(n.value, ir.Var) and isinstance(n.value.storage, ir.Io)
                ops[n.pointer.storage.sym] = "dap" if n.addr else "dio" if io else "dac"
            elif isinstance(n, ir.IndirectCall) and n.home:
                ops[n.pointer.storage.sym] = "jmp"
            elif isinstance(n, ir.Assign) and isinstance(n.value, ir.HomeLoad):
                op = "lio" if isinstance(n.target, ir.Var) and isinstance(n.target.storage, ir.Io) else "lac"
                ops[n.value.pointer.storage.sym] = op
            elif isinstance(n, ir.HomeLoad):
                ops.setdefault(n.pointer.storage.sym, "lac")
    return ops


def _tag_first_word(items: list[ir.Item], rule: str) -> list[ir.Item]:
    """The word a fallthrough reaches carries the rule that made it adjacent."""
    n = next(i for i, it in enumerate(items) if isinstance(it, ir.Word))
    return items[:n] + [replace(items[n], via=items[n].via + (rule,))] + items[n + 1:]


def attach_labels(items: list[ir.Item]) -> list[ir.Emitted]:
    words: list[ir.Emitted] = []
    pending: list[str] = []
    defined: set[str] = set()
    for it in items:
        if isinstance(it, ir.LabelDef):
            if it.name in defined:
                raise LayoutError(f"{it.name} is defined twice (a HOMED object has one home)")
            defined.add(it.name)
            pending.append(it.name)
            continue
        if isinstance(it, (ir.Break, ir.Origin)):
            if pending:
                raise LayoutError(f"labels {pending} come before an origin")
            words.append(it)
            continue
        if pending:
            it = replace(it, labels=tuple(pending))
            pending = []
        words.append(it)
    if pending:
        raise LayoutError(f"labels {pending} name no word")
    return words
