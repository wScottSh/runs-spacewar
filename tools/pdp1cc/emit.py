"""Word list -> Macro text: one line per word, rule id in the comment."""
from __future__ import annotations

from . import ir

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


def line_text(w: ir.Emitted, trace: bool = True) -> str:
    if isinstance(w, ir.Origin):
        line = f"{w.n:o}/"
    elif isinstance(w, ir.PoolPlacement):
        line = f"\t{w.name}"
    elif isinstance(w, ir.StartAddress):
        line = f"\tstart {w.sym}"
    else:
        label = "".join(f"{lab}, " for lab in w.labels)[:-1]
        line = f"{label}\t" + (f". {w.n:o}/" if isinstance(w, ir.Reserve) else word_text(w))
    if trace:
        note = getattr(w, "note", "")
        line += f"\t/ {w.rule}" + "".join(f" +{v}" for v in w.via) + (f" {note}" if note else "")
    return line


def emit(words: list[ir.Emitted], trace: bool = True) -> str:
    return "".join(line_text(w, trace) + "\n" for w in words)


def program(title: str, units: list[list[ir.Emitted]], trace: bool = True,
            tail: str = "", default_start: int | None = None) -> str:
    """One Macro program: macro1 reads the first line as the title, then the
    units in order, then tail. The program ends with its start address: the
    `start` of the unit with a START function, else default_start. macro1
    ends a tape at `start`, so it comes last."""
    starts = [w for words in units for w in words if isinstance(w, ir.StartAddress)]
    if len(starts) > 1:
        raise ValueError(f"a program starts at one START function: {[s.sym for s in starts]}")
    body = "".join(emit([w for w in words if not isinstance(w, ir.StartAddress)], trace)
                   for words in units)
    end = emit(starts, trace) if starts else \
        f"\tstart {default_start:o}\n" if default_start is not None else ""
    return f"{title}\n{body}{tail}{end}"
