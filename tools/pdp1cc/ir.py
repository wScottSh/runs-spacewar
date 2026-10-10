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
class Entry:        # JDA first parameter, or an ENTRY_CELL name: a function's entry word
    sym: str
    alias: bool = False


@dataclass(frozen=True)
class ByName:       # BYNAME parameter: the caller's inline word, fetched with xct
    name: str


@dataclass(frozen=True)
class Inline:       # INLINE parameter: the constant word after the call, read with `lac i R`
    name: str


@dataclass(frozen=True)
class Pool:         # POOL object: a `\x` word macro1 allocates at `variables`
    sym: str


@dataclass(frozen=True)
class Homed:        # HOMED pointer: the address field of its home instruction
    sym: str
    init: "Sym | Num | None" = None     # the home's address before the first store; None: `.`


Storage = Union[Acc, Io, Placed, Extern, Entry, ByName, Inline, Pool, Homed]
Memory = (Placed, Extern, Entry, Pool)


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
class Rot:              # ral/rar(ac, n), ril/rir(io, n): one register rotated
    op: str
    operand: Var
    count: int


@dataclass(frozen=True)
class PairOp:           # rcl(h, l, n) / mus(h, l, m) etc: h in AC, l in IO, both updated
    op: str
    hi: Var
    lo: Var
    count: int | None = None        # shift count, or
    operand: Expr | None = None     # memory operand of a multiply/divide step


@dataclass(frozen=True)
class Param:
    name: str
    kind: str           # "ac": entry word / AC, "io": register, "byname" / "inline": a word after the call
    pointer: bool = False


@dataclass(frozen=True)
class Signature:
    name: str           # C name
    sym: str            # Macro symbol of the entry
    conv: str           # "jda" | "block" | "xct" | "jsp" | "inline" (static inline: laid out at each call)
    params: tuple[Param, ...]
    returns: str        # "word" | "word*" | "dword" | "void"
    exit_sym: str       # the cell returns go through: exit `jmp .` or the by-name `xct`

    @property
    def inline_count(self) -> int:
        """Words after the call that the function returns past."""
        return sum(p.kind in ("byname", "inline") for p in self.params)

    @property
    def byname(self) -> bool:
        """Returns through the by-name `xct` cell (`jmp i R`), not an exit `jmp .`."""
        return any(p.kind == "byname" for p in self.params)


@dataclass(frozen=True)
class Call:             # f(args): a JDA call, or a tail call of a BLOCK
    sig: Signature
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class CodeRef:          # a function's name as a value: its address
    sig: Signature


@dataclass(frozen=True)
class IndirectCall:     # p(args) through a pointer-to-function object p
    pointer: Var
    sig: Signature      # the pointed-to function type
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class Hw:               # a hardware builtin with no operand: tyi(), lsm()
    name: str


@dataclass(frozen=True)
class Insn:             # an instruction word built by an I_* constructor: a constant
    op: str             # mnemonic or microcode expression, e.g. "lac", "dpy-4000"
    operand: "Operand | None" = None
    i: bool = False


@dataclass(frozen=True)
class AddrOf:           # &object, or an array's name, as a value: its address
    operand: "Sym"


@dataclass(frozen=True)
class HomeLoad:         # *home(p): the home instruction of homed pointer p
    pointer: Var


@dataclass(frozen=True)
class Half:             # call.hi / call.lo of a dword result
    call: Call
    which: str


@dataclass(frozen=True)
class Pair:             # (dword){ hi, lo }
    hi: Expr
    lo: Expr


@dataclass(frozen=True)
class Flag:             # stf(n) / clf(n): set or clear program flag n
    op: str
    n: int


@dataclass(frozen=True)
class Dpy:              # dpy(x, y, n) / dpy_nowait(x, y): plot (AC, IO)
    x: "Expr"
    y: Var
    intensity: int | None   # None: dpy_nowait, which asks for a completion pulse


@dataclass(frozen=True)
class HomeWord:         # I_LIO(p) / I_LIO(++p) for a HOMED p: its home instruction word
    pointer: Var
    op: str
    increment: bool


Expr = Union[Const, Var, PreInc, Neg, Binary, Shift, Rot, PairOp, Call, Half, Pair, CodeRef,
             IndirectCall, Hw, Insn, AddrOf, HomeLoad, Flag, Dpy, HomeWord]


@dataclass(frozen=True)
class Compare:          # e <op> 0, or e == m / e != m (sas, sad)
    op: str
    operand: Expr
    against: Expr | None = None


@dataclass(frozen=True)
class FlagTest:         # flag(n), or !flag(n) when negated
    n: int
    negated: bool = False


@dataclass(frozen=True)
class SenseTest:        # sense(n), or !sense(n) when negated: sense switch n
    n: int
    negated: bool = False


# -------------------------------------------------------------- statements

@dataclass(frozen=True)
class Assign:
    target: Var
    value: Expr


@dataclass(frozen=True)
class AssignPair:       # dword p = f(...): p.hi in AC, p.lo in IO
    hi: Var
    lo: Var
    value: Expr


@dataclass(frozen=True)
class Eval:             # expression statement for its effect
    expr: Expr


@dataclass(frozen=True)
class Goto:
    label: str


@dataclass(frozen=True)
class Labeled:
    label: str
    stmt: Stmt


@dataclass(frozen=True)
class Unroll:           # for (int i = 0; i < n; i++) S with i unused: S n times
    count: int
    body: Stmt


@dataclass(frozen=True)
class SkipReturn:       # skip_return(): return one word further
    pass


@dataclass(frozen=True)
class ArgsDone:         # the inline-parameter skip, placed by inline.place_args
    pass


@dataclass(frozen=True)
class StoreNext:        # *p++ = e: store through p, then advance p
    pointer: Var
    value: Expr


@dataclass(frozen=True)
class AssignAddr:       # x.addr = e, or p = e for a homed p: e's address bits into x (dap)
    target: Var
    value: Expr


@dataclass(frozen=True)
class Switch:           # switch ((int)e) over cases 0..n: a jump table
    value: Expr
    slots: tuple["Stmt | None", ...]     # cases 0..n-1: a Goto, or None to fall into the next
    last: "Stmt"                         # case n: laid out in its slot


@dataclass(frozen=True)
class PlaceHere:        # PLACE(x, ...): these words are laid out here
    data: tuple["Datum", ...]


@dataclass(frozen=True)
class OprCombine:       # a, b, c; as one statement: one operate-group instruction
    parts: tuple["Stmt", ...]


@dataclass(frozen=True)
class HomedSwitch:      # switch ((int)i) for a HOMED word i: Duff's device, entered by i's home
    index: Var
    table: str                       # label of case 0
    cases: tuple["Stmt", ...]        # cases 0..n-1, each falling into the next
    last: "Stmt"


@dataclass(frozen=True)
class If:
    cond: "Compare | FlagTest | SenseTest"
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


Stmt = Union[Assign, AssignPair, Eval, If, Forever, Continue, Return, Block, Goto, Labeled,
             Unroll, SkipReturn, ArgsDone, StoreNext, AssignAddr, Switch, PlaceHere, OprCombine,
             HomedSwitch]


# ----------------------------------------------------------- unit structure

@dataclass(frozen=True)
class Function:
    sig: Signature
    params: tuple[Var, ...]
    body: Block
    at: int | None = None       # AT(a): laid out from address a

    @property
    def sym(self) -> str:
        return self.sig.sym


@dataclass(frozen=True)
class Datum:
    sym: str
    values: tuple["int | Insn | Sym", ...]  # one per word: a number, an instruction word or an address
    name: str           # C name
    at: int | None = None
    array: bool = False


@dataclass(frozen=True)
class Space:            # RESERVE object: words set aside here, not punched
    sym: str
    size: int
    name: str
    at: int | None = None
    array: bool = False
    pointer: bool = False


@dataclass(frozen=True)
class RegionBreak:      # REGION_BREAK(): the following items go to the region's next line range
    at: None = None


TopItem = Union[Function, Datum, Space, RegionBreak]


@dataclass(frozen=True)
class Unit:
    items: tuple[TopItem, ...]
    signatures: dict[str, Signature]
    next_label: int     # generated symbols already used: layout continues from here
    objects: dict[str, Storage]     # file-scope objects by C name
    data: dict[str, Datum] = None   # every initialized word or array, by C name, wherever placed
    inlines: dict[str, Function] = None     # static inline functions, laid out at each call

    def words(self, name: str) -> int:
        """Words a file-scope object spans."""
        if name in (self.data or {}):
            return len(self.data[name].values)
        return next((s.size for s in self.items if isinstance(s, Space) and s.name == name), 1)


# ------------------------------------------------------------------ output
# Operands stay symbolic: macro1 resolves every address.

@dataclass(frozen=True)
class Sym:
    name: str
    pool: bool = False  # a POOL object: written `\name`
    offset: int = 0     # a later word of an array: `name+n`


@dataclass(frozen=True)
class Num:
    value: int


@dataclass(frozen=True)
class Lit:              # `(x`: a constants-pool literal
    value: "Num | Insn"


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
    via: tuple[str, ...] = ()   # rules that shaped this word without emitting their own


@dataclass(frozen=True)
class LabelDef:
    name: str


@dataclass(frozen=True)
class Place:
    """A location directive, not a word: `a/` (origin) or `. n/` (reserve n)."""
    kind: str           # "origin" | "reserve"
    n: int
    rule: str
    labels: tuple[str, ...] = ()
    via: tuple[str, ...] = ()


@dataclass(frozen=True)
class Break:
    """REGION_BREAK: the end of one chunk of a region's Macro text."""
    labels: tuple[str, ...] = ()


Item = Union[Word, LabelDef, Place, Break]
