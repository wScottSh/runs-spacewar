"""Word list -> Macro text: one line per word, rule id in the comment."""
from __future__ import annotations

from . import ir


def operand_text(o: ir.Operand) -> str:
    match o:
        case ir.Sym(name=n):
            return n
        case ir.Num(value=v):
            return f"{v:o}"
        case ir.Lit(value=v):
            return "(" + operand_text(v)
        case ir.Here():
            return "."
        case ir.ShiftCount(n=n):
            return f"{n}s"
    raise TypeError(o)


def word_text(w: ir.Word) -> str:
    parts = [w.op] if w.op else []
    if w.i:
        parts.append("i")
    if w.operand is not None:
        parts.append(operand_text(w.operand))
    return " ".join(parts)


def emit(words: list[ir.Word], trace: bool = True) -> str:
    lines = []
    for w in words:
        label = f"{w.labels[0]}," if w.labels else ""
        line = f"{label}\t{word_text(w)}"
        if trace:
            line += f"\t/ {w.rule}" + (f" {w.note}" if w.note else "")
        lines.append(line)
    return "\n".join(lines) + "\n"
