"""Orders a unit's items in C definition order (LAY-ORDER), attaches labels
to the word they name, and merges labels that land on the same cell."""
from __future__ import annotations

from dataclasses import replace

from . import ir
from .select import FunctionLowerer, W


class LayoutError(Exception):
    pass


def place(unit: ir.Unit, label_prefix: str) -> list[ir.Word]:
    items: list[ir.Item] = []
    counter = 0
    for top in unit.items:
        match top:
            case ir.Function():
                fl = FunctionLowerer(top, label_prefix, counter)
                items += fl.lower()
                counter = fl.counter
            case ir.Datum():
                items += [ir.LabelDef(top.sym), W(None, "ST-PLACED", ir.Num(top.value))]
    return attach_labels(items)


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
