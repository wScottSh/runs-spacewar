"""Orders a unit's items in C definition order (LAY-ORDER), attaches labels
to the word they name, and merges labels that land on the same cell."""
from __future__ import annotations

from dataclasses import replace

from . import ir
from .dialect import Namer
from .select import FunctionLowerer, W


class LayoutError(Exception):
    pass


def place(unit: ir.Unit, label_prefix: str) -> list[ir.Word]:
    namer = Namer(label_prefix, unit.next_label)
    items: list[ir.Item] = []
    entered_by_fallthrough = False
    for n, top in enumerate(unit.items):
        match top:
            case ir.Function():
                following = unit.items[n + 1].sym if n + 1 < len(unit.items) else None
                lowerer = FunctionLowerer(top, namer, following)
                own = lowerer.lower()
                if entered_by_fallthrough:
                    own = _tag_first_word(own, "LAY-FALLTHROUGH")
                entered_by_fallthrough = lowerer.fell_through
                items += own
            case ir.Datum():
                items += [ir.LabelDef(top.sym), W(None, "ST-PLACED", ir.Num(top.value))]
    return attach_labels(items)


def _tag_first_word(items: list[ir.Item], rule: str) -> list[ir.Item]:
    """The word a fallthrough reaches carries the rule that made it adjacent."""
    n = next(i for i, it in enumerate(items) if isinstance(it, ir.Word))
    return items[:n] + [replace(items[n], via=items[n].via + (rule,))] + items[n + 1:]


def attach_labels(items: list[ir.Item]) -> list[ir.Word]:
    words: list[ir.Word] = []
    pending: list[str] = []
    alias: dict[str, str] = {}
    for it in items:
        if isinstance(it, ir.LabelDef):
            pending.append(it.name)
            continue
        if pending:
            for extra in pending[1:]:
                alias[extra] = pending[0]
            it = replace(it, labels=(pending[0],))
            pending = []
        words.append(it)
    if pending:
        raise LayoutError(f"labels {pending} name no word")
    return [_rename(w, alias) for w in words]


def _rename(w: ir.Word, alias: dict[str, str]) -> ir.Word:
    if isinstance(w.operand, ir.Sym) and w.operand.name in alias:
        return replace(w, operand=ir.Sym(alias[w.operand.name]))
    return w
