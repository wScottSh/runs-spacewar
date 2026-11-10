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
    exits, exitless = exit_cells([t for t in unit.items if isinstance(t, ir.Function)])
    for n, top in enumerate(unit.items):
        if top.at is not None:
            items.append(ir.Origin(top.at, check("LAY-AT")))
        match top:
            case ir.Directive(name=name):
                items.append(ir.PoolPlacement(name, check("LAY-POOL")))
            case ir.Function():
                after = unit.items[n + 1] if n + 1 < len(unit.items) else None
                following = after.sym if isinstance(after, (ir.Function, ir.Datum, ir.Space)) and \
                    after.at is None else None
                lowerer = FunctionLowerer(top, namer, following, keeps_io, inlines, homes, exitless,
                                          exits=exits)
                own = lowerer.lower()
                if top.shared_tails:
                    own = cross_jump(own, namer)
                keeps_io[top.sym] = preserves_io(own) and not lowerer.fell_through
                if entered_by_fallthrough:
                    own = _tag_first_word(own, "LAY-FALLTHROUGH")
                entered_by_fallthrough = lowerer.fell_through
                items += own
            case ir.Datum():
                items += datum_words(top)
            case ir.Space():
                items += [ir.LabelDef(top.sym), ir.Reserve(top.size, check("ST-RESERVE"))]
    if unit.start is not None:
        items.append(ir.StartAddress(unit.start, check("LAY-START")))
    labels = {i.name for i in items if isinstance(i, ir.LabelDef)}
    homeless = [name for name, s in unit.objects.items() if isinstance(s, ir.HomedInsn)
                and s.sym not in labels]
    if homeless:
        raise LayoutError(f"HOMED shift {', '.join(homeless)} has no home: run it with xct(x, ...)")
    homeless = [name for name, s in unit.objects.items()
                if isinstance(s, ir.Homed) and s.here and s.sym not in labels]
    if homeless:
        raise LayoutError(f"HOMED pointer {', '.join(homeless)} has no home: use it once as "
                          "*home(p), or declare it extern when other text holds its home")
    return attach_labels(items)


SKIPS = {"sza", "spa", "sma", "spi", "szf", "szs", "szo", "sas", "sad", "isp", "skp"}


def _skips(w: ir.Word) -> bool:
    return w.op is not None and (w.op.split()[0] in SKIPS or "skip" in w.op)


def _same(a: ir.Word, b: ir.Word) -> bool:
    return (a.op, a.operand, a.i) == (b.op, b.operand, b.i)


def cross_jump(items: list[ir.Item], namer: Namer) -> list[ir.Item]:
    """Paths that join at a label and end with the same words share one
    copy of them (CROSS-JUMP): the path that falls into the label keeps
    its words, and a path that jumps there jumps to the first word they
    share instead. A shared run neither ends in a skip nor follows one on
    the jumping path, and no other path enters it there."""
    changed = True
    while changed:
        changed = False
        for j, w in enumerate(items):
            if not (isinstance(w, ir.Word) and w.op == "jmp" and not w.i and isinstance(w.operand, ir.Sym)):
                continue
            label = next((n for n, i in enumerate(items)
                          if isinstance(i, ir.LabelDef) and i.name == w.operand.name), None)
            if label is None:
                continue
            fall = [n for n in range(label) if isinstance(items[n], ir.Word)]
            if not fall or items[fall[-1]].op == "jmp" or _skips(items[fall[-1]]):
                continue                    # no path falls into the label
            matched, a = [], j - 1
            while a >= 0 and isinstance(items[a], ir.Word) and len(matched) < len(fall) \
                    and a != fall[-1 - len(matched)] and _same(items[a], items[fall[-1 - len(matched)]]):
                matched.append(a)
                a -= 1
            while matched and (_skips(items[matched[0]]) or a >= 0 and isinstance(items[a], ir.Word)
                               and _skips(items[a])):
                a = matched.pop()           # a shared run neither ends in a skip nor follows one
            if not matched or not (matched[-1] > label or j < fall[-len(matched)]):
                continue
            first = fall[-len(matched)]
            if isinstance(items[first - 1], ir.LabelDef):
                name, ins = items[first - 1].name, []
            else:
                name = namer.fresh()
                ins = [ir.LabelDef(name)]
            jump = W("jmp", "CROSS-JUMP", ir.Sym(name))
            items = items[:first] + ins + items[first:]
            shift = len(ins) if first < matched[-1] else 0
            lo, hi = matched[-1] + shift, j + shift
            items = items[:lo] + [jump] + items[hi + 1:]
            changed = True
            break
    return items


def exit_cells(functions: list[ir.Function]) -> tuple[dict[str, str], frozenset[str]]:
    """The exit cell each function returns through. One whose returns all
    tail-call one BLOCK defined here returns through that block's exit
    cell, so a function adopting it patches that cell (LAY-ADOPT). The
    second result names the functions whose chain ends in a BLOCK that
    tail-calls several BLOCKs: they have no exit to share."""
    defined = {f.sig.name: f for f in functions}

    def resolve(f: ir.Function, seen: frozenset[str]) -> ir.Function:
        tails = _tail_calls(f.body)
        targets = {r.value.sig.name for r in tails}
        plain = [r for r in _returns(f.body) if r not in tails and not isinstance(r.value, ir.IndirectCall)]
        if plain or len(targets) != 1 or (target := targets.pop()) not in defined or target in seen:
            return f
        return resolve(defined[target], seen | {f.sig.name})
    ends = {f.sig.name: resolve(f, frozenset()) for f in functions}
    exitless = frozenset(name for name, end in ends.items()
                         if end.sig.conv is ir.Conv.BLOCK and len(tail_targets(end)) > 1)
    return {name: end.sig.exit_sym for name, end in ends.items()}, exitless


def home_ops(functions: list[ir.Function]) -> dict[str, str]:
    """The instruction at each HOMED pointer's home: what *home(p) does there."""
    ops: dict[str, str] = {}
    for fn in functions:
        for n in inline.iter_nodes(fn.body):
            if isinstance(n, ir.Xct) and isinstance(n.insn, ir.HomeLoad):
                ops[n.insn.pointer.storage.sym] = "xct"
            elif isinstance(n, ir.Binary) and isinstance(n.right, ir.HomeLoad):
                ops[n.right.pointer.storage.sym] = BIN_MNEMONIC[n.op]
            elif isinstance(n, ir.HomeStore):
                io = isinstance(n.value, ir.Var) and isinstance(n.value.storage, ir.Io)
                ops[n.pointer.storage.sym] = "dap" if n.addr else "dzm" if n.value == ir.Const(0) else \
                    "dio" if io else "dac"
            elif isinstance(n, ir.IndirectCall) and n.home:
                ops[n.pointer.storage.sym] = "jmp"
            elif isinstance(n, ir.Assign) and isinstance(n.value, ir.HomeLoad):
                op = "lio" if isinstance(n.target, ir.Var) and isinstance(n.target.storage, ir.Io) else "lac"
                ops[n.value.pointer.storage.sym] = op
            elif isinstance(n, ir.HomeLoad):
                ops.setdefault(n.pointer.storage.sym, "lac")
    return ops


def tail_targets(fn: ir.Function) -> set[str]:
    return {n.value.sig.name for n in inline.iter_nodes(fn.body) if isinstance(n, ir.Return)
            and isinstance(n.value, ir.Call) and n.value.sig.conv is ir.Conv.BLOCK}


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
        if isinstance(it, (ir.Origin, ir.PoolPlacement, ir.StartAddress)):
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
