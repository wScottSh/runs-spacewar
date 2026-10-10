"""Word list -> Macro text: one line per word, rule id in the comment."""
from __future__ import annotations

from . import ir

BREAK = "/ region break"


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


def line_text(w: ir.Word | ir.Origin | ir.Reserve, trace: bool = True) -> str:
    if isinstance(w, ir.Origin):
        line = f"{w.n:o}/"
    else:
        label = "".join(f"{lab}, " for lab in w.labels)[:-1]
        line = f"{label}\t" + (f". {w.n:o}/" if isinstance(w, ir.Reserve) else word_text(w))
    if trace:
        note = getattr(w, "note", "")
        line += f"\t/ {w.rule}" + "".join(f" +{v}" for v in w.via) + (f" {note}" if note else "")
    return line


def regions(words: list[ir.Emitted], trace: bool = True) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for w in words:
        if isinstance(w, ir.Break):
            out.append([])
        else:
            out[-1].append(line_text(w, trace))
    return out


def emit(words: list[ir.Emitted], trace: bool = True) -> str:
    lines = [line for n, region in enumerate(regions(words, trace))
             for line in ([BREAK] if n else []) + region]
    return "\n".join(lines) + "\n"
