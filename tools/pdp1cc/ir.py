"""Domain types. No pycparser type crosses this module's users' boundaries."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Union

WORD_BITS = 18
WORD_MASK = (1 << WORD_BITS) - 1
ADDR_MASK = (1 << 12) - 1
AC_ROTATES = {"ral", "rar"}
IO_ROTATES = {"ril", "rir"}
DPY_NOWAIT = "dpy-4000"     # plot, and ask for a completion pulse


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
    init: "Sym | Num | None" = None
    here: bool = True   # defined in this file, so its home is here; extern: in other text


@dataclass(frozen=True)
class Element:      # a[k] with k constant: the word k past the start of a file-scope array
    sym: str
    offset: int


@dataclass(frozen=True)
class HomedInsn:    # HOMED insn: the instruction at its home, executed where it stands
    sym: str
    init: "Insn"


Storage = Union[Acc, Io, Placed, Extern, Entry, ByName, Inline, Pool, Homed, HomedInsn, Element]
Memory = (Placed, Extern, Entry, Pool, HomedInsn, Element)


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
    target: "Var | Deref"


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
class PairShift:        # rcl(h, l, n) etc: h in AC, l in IO, shifted as one
    op: str
    hi: Var
    lo: Var
    count: int


@dataclass(frozen=True)
class PairStep:         # mus(h, l, m) / dis(h, l, m)
    op: str
    hi: Var
    lo: Var
    operand: Expr


class Conv(Enum):
    JDA = "jda"
    JSP = "jsp"
    XCT = "xct"
    BLOCK = "block"
    INLINE = "inline"


class ParamKind(Enum):
    AC = "ac"
    IO = "io"
    BYNAME = "byname"
    INLINE = "inline"

    @property
    def after_call(self) -> bool:
        return self in (ParamKind.BYNAME, ParamKind.INLINE)


@dataclass(frozen=True)
class Param:
    name: str
    kind: ParamKind
    pointer: bool = False


@dataclass(frozen=True)
class Signature:
    name: str           # C name
    sym: str            # Macro symbol of the entry
    conv: Conv
    params: tuple[Param, ...]
    returns: str        # "word" | "word*" | "dword" | "io" (a word returned in IO) | "void"
    exit_sym: str       # the cell returns go through: exit `jmp .` or the by-name `xct`

    @property
    def inline_count(self) -> int:
        """Words after the call that the function returns past."""
        return sum(p.kind.after_call for p in self.params)

    @property
    def byname(self) -> bool:
        """Returns through the by-name `xct` cell (`jmp i R`), not an exit `jmp .`."""
        return any(p.kind is ParamKind.BYNAME for p in self.params)


@dataclass(frozen=True)
class Call:             # f(args): a JDA call, or a tail call of a BLOCK
    sig: Signature
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class CodeRef:          # a function's name as a value: its address, with flags above it
    sig: Signature
    flags: int = 0


@dataclass(frozen=True)
class IndirectCall:     # p(args) through a pointer-to-function object p
    pointer: Var
    sig: Signature      # the pointed-to function type
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class ComputedCall:     # ((f *)e)(): a call of the routine whose address e's address field holds
    target: Expr
    sig: Signature


@dataclass(frozen=True)
class Halt:             # halt(ac, io): stop with ac and io on the console lights
    ac: "Expr"
    io: "Var"


@dataclass(frozen=True)
class Swapped:          # SWAP(x): x moved between AC and IO by the swap rotation (rcl)
    operand: "Expr"


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
class Dpy:              # dpy(x, y, n)
    x: "Expr"
    y: Var
    intensity: int


@dataclass(frozen=True)
class DpyNowait:        # dpy_nowait(x, y)
    x: "Expr"
    y: Var


@dataclass(frozen=True)
class HomeWord:
    pointer: Var
    op: str
    increment: bool


@dataclass(frozen=True)
class Deref:            # *p: the word p points to, named through p with the indirect bit
    pointer: Var


@dataclass(frozen=True)
class Xct:              # xct(w, a) / xct(w, hi, lo): execute instruction word w on AC (and IO)
    insn: "Insn | HomeLoad | Var"
    hi: "Expr"
    lo: Var | None = None


Expr = Union[Const, Var, PreInc, Neg, Binary, Shift, Rot, PairShift, PairStep, Call, Half, Pair,
             CodeRef, IndirectCall, Hw, Insn, AddrOf, HomeLoad, Flag, Dpy, DpyNowait, HomeWord,
             Deref, Xct, ComputedCall, Halt, Swapped]


@dataclass(frozen=True)
class Compare:
    op: str
    operand: Expr
    against: Expr | None = None
    skipnot: bool = False   # SKIPNOT(c): skip on c's own skip with the i bit flipped


@dataclass(frozen=True)
class FlagTest:         # flag(n), or !flag(n) when negated
    n: int
    negated: bool = False


@dataclass(frozen=True)
class SenseTest:
    n: int
    negated: bool = False


# -------------------------------------------------------------- statements

@dataclass(frozen=True)
class Assign:
    target: "Var | Deref | HomeLoad"
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
    at: str = ""


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
class OprCombine:
    parts: tuple["Stmt", ...]


@dataclass(frozen=True)
class HomedSwitch:
    index: Var
    table: str
    cases: tuple["Stmt", ...]
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
    values: tuple["int | Insn | Sym", ...]
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
class RegionBreak:
    at: None = None


@dataclass(frozen=True)
class Directive:        # CONSTANTS() / VARIABLES(): where macro1 places the literal or pool words
    name: str
    at: None = None


TopItem = Union[Function, Datum, Space, RegionBreak, Directive]


@dataclass(frozen=True)
class Unit:
    items: tuple[TopItem, ...]
    signatures: dict[str, Signature]
    next_label: int     # generated symbols already used: layout continues from here
    objects: dict[str, Storage]     # file-scope objects by C name
    data: dict[str, Datum] = None   # every initialized word or array, by C name, wherever placed
    inlines: dict[str, Function] = None

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
    offset: int = 0


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
class InlineBody:
    function: str


@dataclass(frozen=True)
class UnrolledBody:
    at: str


Construct = Union[InlineBody, UnrolledBody]


@dataclass(frozen=True)
class Copy:
    construct: Construct
    instance: str


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
    copies: tuple[Copy, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class LabelDef:
    name: str


@dataclass(frozen=True)
class Origin:
    n: int
    rule: str
    via: tuple[str, ...] = ()


@dataclass(frozen=True)
class Reserve:
    n: int
    rule: str
    labels: tuple[str, ...] = ()
    via: tuple[str, ...] = ()


@dataclass(frozen=True)
class Break:
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class PoolPlacement:    # `constants` / `variables`: macro1 lays the literal or pool words out here
    name: str
    rule: str
    via: tuple[str, ...] = ()


Item = Union[Word, LabelDef, Origin, Reserve, Break, PoolPlacement]
Emitted = Union[Word, Origin, Reserve, Break, PoolPlacement]
