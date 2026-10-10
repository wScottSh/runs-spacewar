"""Orders a unit's items in C definition order (LAY-ORDER), attaches labels
to the word they name, and merges labels that land on the same cell."""
from __future__ import annotations

from dataclasses import replace

from . import ir
from .dialect import Namer
from .rules import check
from .select import FunctionLowerer, W, datum_words, preserves_io


class LayoutError(Exception):
    pass


def place(unit: ir.Unit, label_prefix: str) -> list[ir.Word]:
    namer = Namer(label_prefix, unit.next_label)
    items: list[ir.Item] = []
    entered_by_fallthrough = False
    keeps_io: dict[str, bool] = {}
    for n, top in enumerate(unit.items):
        if top.at is not None:
            items.append(ir.Place("origin", top.at, check("LAY-AT")))
        match top:
            case ir.Function():
                after = unit.items[n + 1] if n + 1 < len(unit.items) else None
                following = after.sym if after is not None and after.at is None else None
                lowerer = FunctionLowerer(top, namer, following, keeps_io)
                own = lowerer.lower()
                keeps_io[top.sym] = preserves_io(own) and not lowerer.fell_through
                if entered_by_fallthrough:
                    own = _tag_first_word(own, "LAY-FALLTHROUGH")
                entered_by_fallthrough = lowerer.fell_through
                items += own
            case ir.Datum():
                items += datum_words(top)
            case ir.Space():
                items += [ir.LabelDef(top.sym), ir.Place("reserve", top.size, check("ST-RESERVE"))]
    return attach_labels(items)


def _tag_first_word(items: list[ir.Item], rule: str) -> list[ir.Item]:
    """The word a fallthrough reaches carries the rule that made it adjacent."""
    n = next(i for i, it in enumerate(items) if isinstance(it, ir.Word))
    return items[:n] + [replace(items[n], via=items[n].via + (rule,))] + items[n + 1:]


def attach_labels(items: list[ir.Item]) -> list[ir.Word | ir.Place]:
    """Labels name the next word, or the next reserved space."""
    words: list[ir.Word | ir.Place] = []
    pending: list[str] = []
    alias: dict[str, str] = {}
    defined: set[str] = set()
    for it in items:
        if isinstance(it, ir.LabelDef):
            if it.name in defined:
                raise LayoutError(f"{it.name} is defined twice (a HOMED pointer has one home)")
            defined.add(it.name)
            pending.append(it.name)
            continue
        if isinstance(it, ir.Place) and it.kind == "origin":
            if pending:
                raise LayoutError(f"labels {pending} come before an origin")
            words.append(it)
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


def _rename(w: ir.Word | ir.Place, alias: dict[str, str]) -> ir.Word | ir.Place:
    if isinstance(w, ir.Word) and isinstance(w.operand, ir.Sym) and w.operand.name in alias:
        return replace(w, operand=ir.Sym(alias[w.operand.name]))
    return w
