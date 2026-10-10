"""Word list -> Macro text: one line per word, rule id in the comment."""
from __future__ import annotations

from . import ir

BREAK = "/ region break"     # where one line range of a region ends and the next begins


def operand_text(o: ir.Operand) -> str:
    match o:
        case ir.Sym(name=n, pool=pool, offset=off):
            return ("\\" if pool else "") + n + (f"+{off:o}" if off else "")
        case ir.Insn():
            return insn_text(o)
        case ir.Num(value=v):
            return f"{v:o}"
        case ir.Lit(value=v):
            return "(" + operand_text(v)
        case ir.Here():
            return "."
        case ir.ShiftCount(n=n):
            return f"{n}s"
    raise TypeError(o)


def insn_text(n: ir.Insn) -> str:
    parts = [n.op] + (["i"] if n.i else []) + ([operand_text(n.operand)] if n.operand else [])
    return " ".join(parts)


def word_text(w: ir.Word) -> str:
    parts = [w.op] if w.op else []
    if w.i:
        parts.append("i")
    if w.operand is not None:
        parts.append(operand_text(w.operand))
    return " ".join(parts)


def emit(words: list[ir.Word | ir.Place], trace: bool = True) -> str:
    lines = []
    for w in words:
        if isinstance(w, ir.Break):
            lines.append(BREAK)
            continue
        label = f"{w.labels[0]}," if w.labels else ""
        if isinstance(w, ir.Place) and w.kind == "origin":
            line = f"{w.n:o}/"
        elif isinstance(w, ir.Place):
            line = f"{label}\t. {w.n:o}/"
        else:
            line = f"{label}\t{word_text(w)}"
        if trace:
            note = getattr(w, "note", "")
            line += f"\t/ {w.rule}" + "".join(f" +{v}" for v in w.via) + (f" {note}" if note else "")
        lines.append(line)
    return "\n".join(lines) + "\n"
