"""ARGS placement: where a function with inline parameters skips them (`idx R`).

The skip goes before the first top-level statement S of the body such that
  - every read of a by-name parameter is in a statement before S,
  - no jump from before S lands after S's own label, and nothing after S jumps
    back to S or before it (S post-dominates the reads and dominates the returns),
  - no return comes before S,
  - AC is dead at S: every AC local is assigned before it is read again.
`idx` overwrites AC, so the last condition is what keeps the skip from
changing what the C means."""
from __future__ import annotations

from dataclasses import fields, is_dataclass

from . import ir


class ArgsError(Exception):
    pass


def place_args(fn: ir.Function) -> ir.Function:
    stmts = list(fn.body.stmts)
    reads = [i for i, s in enumerate(stmts) if any(map(is_byname_read, iter_nodes(s)))]
    acc_names = {v.name for s in stmts for v in _nodes(s, ir.Var) if isinstance(v.storage, ir.Acc)}
    for p in range(max(reads, default=-1) + 1, len(stmts)):
        if _boundary_ok(stmts, p) and not _ac_live(stmts[p:], acc_names):
            stmts[p] = _prepend(stmts[p], ir.ArgsDone())
            return ir.Function(fn.sig, fn.params, ir.Block(tuple(stmts)))
    raise ArgsError(f"{fn.sig.name}: no statement boundary after the last by-name read where "
                    "AC is dead and every path to a return passes")


def _boundary_ok(stmts: list[ir.Stmt], p: int) -> bool:
    before, here, after = stmts[:p], stmts[p], stmts[p + 1:]
    own = here.label if isinstance(here, ir.Labeled) else None
    inside_here = _labels(here.stmt if own else here)
    targets_before = {g.label for s in before for g in _nodes(s, ir.Goto)}
    if targets_before & (inside_here | {lab for s in after for lab in _labels(s)}):
        return False
    targets_after = {g.label for s in [here] + after for g in _nodes(s, ir.Goto)}
    if targets_after & ({lab for s in before for lab in _labels(s)} | ({own} if own else set())):
        return False
    return not any(_nodes(s, ir.Return) for s in before)


def _ac_live(stmts: list[ir.Stmt], names: set[str]) -> bool:
    undecided = set(names)
    for s in stmts:
        used = {v.name for v in _nodes(s, ir.Var)} & undecided
        killed = _kills_first(s)
        if used - killed:
            return True
        undecided -= killed
        if not undecided:
            return False
    return False


def _kills_first(s: ir.Stmt) -> set[str]:
    """AC locals that s assigns before reading."""
    match s:
        case ir.Labeled():
            return _kills_first(s.stmt)
        case ir.Block(stmts=(first, *_)):
            return _kills_first(first)
        case ir.Assign(target=ir.Var(storage=ir.Acc()) as t) \
                if t.name not in {v.name for v in _nodes(s.value, ir.Var)}:
            return {t.name}
        case ir.AssignPair() if s.hi.name not in {v.name for v in _nodes(s.value, ir.Var)}:
            return {s.hi.name}
    return set()


def _prepend(s: ir.Stmt, first: ir.Stmt) -> ir.Stmt:
    if isinstance(s, ir.Labeled):
        return ir.Labeled(s.label, _prepend(s.stmt, first))
    return ir.Block((first, s))


def is_byname_read(n) -> bool:
    return isinstance(n, ir.Var) and isinstance(n.storage, ir.ByName)


def _labels(s) -> set[str]:
    return {lab.label for lab in _nodes(s, ir.Labeled)}


def _nodes(node, kind) -> list:
    return [n for n in iter_nodes(node) if isinstance(n, kind)]


def iter_nodes(node):
    """Every IR node under node (statements and expressions), node first."""
    if isinstance(node, tuple):
        for x in node:
            yield from iter_nodes(x)
    elif is_dataclass(node) and not isinstance(node, ir.Signature):
        yield node
        for f in fields(node):
            yield from iter_nodes(getattr(node, f.name))
