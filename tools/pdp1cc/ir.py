"""Domain types. No pycparser type crosses this module's users' boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

WORD_BITS = 18
WORD_MASK = (1 << WORD_BITS) - 1
ADDR_MASK = (1 << 12) - 1


# ---------------------------------------------------------------- storage
# Where a C object lives. Chosen from the declaration alone, never from use.

@dataclass(frozen=True)
class Acc:          # automatic `word` local: the accumulator
    name: str


@dataclass(frozen=True)
class Io:           # `register word` local: the IO register
    name: str


@dataclass(frozen=True)
class Placed:       # initialized file-scope object: a word at its definition
    sym: str


@dataclass(frozen=True)
class Extern:       # declared here, defined by other text (unlifted Macro)
    sym: str


@dataclass(frozen=True)
class Entry:        # JDA first parameter: the function's entry word
    sym: str


Storage = Union[Acc, Io, Placed, Extern, Entry]
Memory = (Placed, Extern, Entry)


def mem_sym(s: Storage) -> str:
    assert isinstance(s, Memory), s
    return s.sym


# ------------------------------------------------------------- expressions

@dataclass(frozen=True)
class Const:
    value: int          # 18-bit pattern, 0..WORD_MASK


@dataclass(frozen=True)
class Var:
    name: str
    storage: Storage


@dataclass(frozen=True)
class PreInc:           # ++x: idx (statement or value) / isp (condition)
    target: Var


@dataclass(frozen=True)
class Neg:              # -x and ~x: cma
    operand: Expr


@dataclass(frozen=True)
class Binary:           # + - & | ^ : operand order is instruction order
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Shift:            # x << n, x >> n with n a compile-time int
    op: str
    operand: Expr
    count: int


@dataclass(frozen=True)
class PairOp:           # rcl(h, l, n) etc: h in AC, l in IO, both updated
    op: str
    hi: Var
    lo: Var
    count: int


Expr = Union[Const, Var, PreInc, Neg, Binary, Shift, PairOp]


@dataclass(frozen=True)
class Compare:          # e <op> 0, the only comparison the skip group makes
    op: str
    operand: Expr


# -------------------------------------------------------------- statements

@dataclass(frozen=True)
class Assign:
    target: Var
    value: Expr


@dataclass(frozen=True)
class Eval:             # expression statement for its effect
    expr: Expr


@dataclass(frozen=True)
class If:
    cond: Compare
    then: Stmt
    orelse: Stmt | None


@dataclass(frozen=True)
class Forever:
    body: Stmt


@dataclass(frozen=True)
class Continue:
    pass


@dataclass(frozen=True)
class Return:
    value: Expr | None


@dataclass(frozen=True)
class Block:
    stmts: tuple[Stmt, ...]


Stmt = Union[Assign, Eval, If, Forever, Continue, Return, Block]


# ----------------------------------------------------------- unit structure

@dataclass(frozen=True)
class Function:
    sym: str
    conv: str                   # "jda"
    param: Var | None
    body: Block
    returns_value: bool


@dataclass(frozen=True)
class Datum:
    sym: str
    value: int


TopItem = Union[Function, Datum]


@dataclass(frozen=True)
class Unit:
    items: tuple[TopItem, ...]


# ------------------------------------------------------------------ output
# Operands stay symbolic: macro1 resolves every address.

@dataclass(frozen=True)
class Sym:
    name: str


@dataclass(frozen=True)
class Num:
    value: int


@dataclass(frozen=True)
class Lit:              # `(x`: a constants-pool literal
    value: Num


@dataclass(frozen=True)
class Here:             # `.`
    pass


@dataclass(frozen=True)
class ShiftCount:       # `ns`
    n: int


Operand = Union[Sym, Num, Lit, Here, ShiftCount]


@dataclass(frozen=True)
class Word:
    """One 18-bit word of output, still symbolic. `op` is a Macro mnemonic
    (or a skip/operate microcode expression); None is a data word."""
    op: str | None
    rule: str
    operand: Operand | None = None
    i: bool = False
    labels: tuple[str, ...] = ()
    note: str = ""      # trace detail, e.g. the skip-table row


@dataclass(frozen=True)
class LabelDef:
    name: str


Item = Union[Word, LabelDef]
