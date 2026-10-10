"""IR -> Item list. Owns AC/IO value tracking (TRACK) and skip selection.

Every lowering step is a pure function (node, State) -> (items, State), so a
loop body, or a whole function with backward gotos, can be lowered again
until the states at its loop heads and labels are a fixpoint."""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass, replace

from . import emit, inline, ir, skips
from .rules import check

BIN_MNEMONIC = {"+": "add", "-": "sub", "&": "and", "|": "ior", "^": "xor"}
SHIFT_MNEMONIC = {"<<": "sal", ">>": "sar"}
IO_SHIFT_MNEMONIC = {"<<": "sil", ">>": "sir"}
# Shift-group instructions that change IO: xct(w, a) cannot run them.
PAIR_OR_IO_SHIFTS = {"rcl", "rcr", "scl", "scr", "ril", "rir", "sil", "sir"}
LAW_MAX = (1 << 12) - 1
SWAP_HALF = 9           # rcr 9s twice exchanges AC and IO
MAX_PASSES = 20
# Instructions that can change IO. A function whose words include none of
# these, and that leaves only through its own exit, preserves IO for its callers.
IO_WRITERS = {"lio", "cli", "tyi", "rcl", "rcr", "scl", "scr", "ril", "rir", "sil", "sir",
              "mus", "dis", "jsp", "jda", "xct"}
LEAVES_ELSEWHERE = {check(r) for r in ("TAIL-CALL", "TAIL-CALL-INDIRECT", "JSP-FORWARD", "RET-INDIRECT")}
# Operate-group instructions a comma expression may join into one word, and
# what each writes. Parts that write different things do not depend on the
# order the hardware applies them in, so the word means the comma expression.
OPR_WRITES = {"cla": "AC", "cma": "AC", "cli": "IO", "clf": "a program flag", "stf": "a program flag"}


class SelectError(Exception):
    pass


@dataclass(frozen=True)
class Local:
    name: str


@dataclass(frozen=True)
class Cell:
    sym: str


@dataclass(frozen=True)
class AddressBits:
    sym: str
    offset: int


@dataclass(frozen=True)
class PointerBits:
    sym: str


@dataclass(frozen=True)
class Outer:
    """A caller's local, carried through a static inline body: it lasts
    while the body leaves that register alone, and no name in the body
    can match it."""
    fact: Local


Fact = Local | Cell | AddressBits | PointerBits | Outer


@dataclass(frozen=True)
class State:
    ac: frozenset[Fact] = frozenset()
    io: frozenset[Fact] = frozenset()

    def write_mem(self, written: Local | Cell) -> State:
        stale = {written} | ({PointerBits(written.sym)} if isinstance(written, Cell) else set())
        return State(self.ac - stale, self.io - stale)

    def without_memory(self) -> State:
        return State(_lasting(self.ac), _lasting(self.io))


def _lasting(facts: frozenset[Fact]) -> frozenset[Fact]:
    return frozenset(f for f in facts if isinstance(f, (Local, AddressBits, Outer)))


def _into_inline(facts: frozenset[Fact]) -> frozenset[Fact]:
    return frozenset(Outer(f) if isinstance(f, Local) else f for f in facts)


def _out_of_inline(facts: frozenset[Fact]) -> frozenset[Fact]:
    return frozenset(f.fact if isinstance(f, Outer) else f for f in facts if not isinstance(f, Local))


def meet(a: State | None, b: State | None) -> State | None:
    if a is None:
        return b
    if b is None:
        return a
    return State(a.ac & b.ac, a.io & b.io)


def address_fact(e: ir.Expr) -> AddressBits | PointerBits | None:
    match e:
        case ir.AddrOf(operand=o) | ir.Insn(operand=ir.Sym() as o):
            return AddressBits(o.name, o.offset)
        case ir.Var(storage=ir.Homed(sym=sym)):
            return PointerBits(sym)
    return None


def fact(v: ir.Var) -> Local | Cell:
    if isinstance(v.storage, ir.Memory):
        return Cell(ir.mem_sym(v.storage))
    if isinstance(v.storage, ir.Homed):
        return Cell(v.storage.sym)
    return Local(v.name)


def W(op, rule, operand=None, i=False, note="", via=()):
    return ir.Word(op, check(rule), operand, i, (), note, tuple(check(r) for r in via))


def _via(v: ir.Var) -> tuple[str, ...]:
    if isinstance(v.storage, ir.Entry) and v.storage.alias:
        return ("ST-ENTRY-CELL",)
    if isinstance(v.storage, ir.Pool):
        return ("ST-POOL",)
    if isinstance(v.storage, ir.Homed):
        return ("ST-HOMED",)
    if isinstance(v.storage, ir.Slot):
        return ("ST-SLOT",)
    return ()


def _via_deref(d: ir.Deref) -> tuple[str, ...]:
    return ("EX-DEREF",) + _via(d.pointer)


def _via_operand(e: ir.Expr) -> tuple[str, ...]:
    """Rules that chose part of a memory operand: a pool or entry-cell name,
    or an instruction constant (and a pool name inside it)."""
    if isinstance(e, ir.Var):
        return _via(e)
    if isinstance(e, ir.Deref):
        return _via_deref(e)
    if isinstance(e, ir.Insn):
        pool = isinstance(e.operand, ir.Sym) and e.operand.pool
        return ("EX-INSN",) + (("ST-POOL",) if pool else ())
    return ()


def mem(v: ir.Var) -> ir.Sym:
    if not isinstance(v.storage, ir.Memory):
        raise SelectError(f"{v.name} is a register local or by-name parameter, not a memory operand")
    return ir.Sym(ir.mem_sym(v.storage), pool=isinstance(v.storage, ir.Pool))


def cell(v: ir.Var) -> ir.Sym:
    """The word an idx or dap names: a memory word, or a homed pointer's home."""
    if isinstance(v.storage, ir.Homed):
        return ir.Sym(v.storage.sym)
    return mem(v)


def preserves_io(items: list[ir.Item]) -> bool:
    """A function whose words never change IO and that returns only through its own exit."""
    return not any(isinstance(w, ir.Word) and (w.op in IO_WRITERS or w.rule in LEAVES_ELSEWHERE
                                               or "LAY-ADOPT" in w.via)
                   for w in items)


def datum_words(d: ir.Datum, via: tuple[str, ...] = ()) -> list[ir.Item]:
    """An initialized word or word array: its label, then one data word per value."""
    items: list[ir.Item] = [ir.LabelDef(d.sym)]
    for v in d.values:
        if isinstance(v, ir.Sym):
            items.append(W(None, "ST-PLACED", v, via=via + (("ST-POOL",) if v.pool else ())))
        elif isinstance(v, ir.Insn):
            items.append(W(None, "ST-PLACED", v, via=via + _via_operand(v)))
        else:
            items.append(W(None, "ST-PLACED", ir.Num(v), via=via))
    return items


def shift_chunks(n: int) -> list[int]:
    if not 0 < n < 36:
        raise SelectError(f"shift count {n} out of range")
    return [9] * (n // 9) + ([n % 9] if n % 9 else [])


def swap() -> list[ir.Word]:
    """Exchange AC and IO: a half turn of the 36-bit pair."""
    return [W("rcr", "EX-MOVE", ir.ShiftCount(SWAP_HALF)) for _ in range(2)]


@dataclass
class _Loop:
    top: str
    continues: list[State] = field(default_factory=list)


@dataclass
class _Instance:
    sig: ir.Signature
    final: ir.Stmt | None
    after: str
    exits: list[State] = field(default_factory=list)


@dataclass
class FunctionLowerer:
    fn: ir.Function
    namer: object                   # dialect.Namer: generated labels continue the unit's numbering
    next_sym: str | None = None     # symbol of the item laid out after this function
    keeps_io: dict[str, bool] = field(default_factory=dict)   # callees laid out earlier
    inlines: dict[str, ir.Function] = field(default_factory=dict)
    home_ops: dict[str, str] = field(default_factory=dict)
    instances: list[_Instance] = field(default_factory=list)
    strides_prev: dict[str, int] = field(default_factory=dict)
    strides_out: dict[str, int] = field(default_factory=dict)
    loops: list[_Loop] = field(default_factory=list)
    adopted: ir.Signature | None = None
    last_return: ir.Return | None = None
    label_prev: dict[str, State] = field(default_factory=dict)
    label_out: dict[str, State | None] = field(default_factory=dict)
    byname_cell_done: bool = False
    fell_through: bool = False      # a tail call elided its jump to the next item

    def label(self) -> str:
        return self.namer.fresh()

    @property
    def sig(self) -> ir.Signature:
        return self.fn.sig

    # ------------------------------------------------------------ function
    def lower(self) -> list[ir.Item]:
        fn = self.fn
        if fn.sig.conv is ir.Conv.JSP and (target := _forwarded(fn.body)) is not None:
            return self.forward(target)
        tails = _tail_calls(fn.body)
        jumps = [r for r in _returns(fn.body) if isinstance(r.value, ir.IndirectCall)]
        plain = [r for r in _returns(fn.body) if r not in tails and r not in jumps]
        if tails:
            targets = {t.value.sig.name for t in tails}
            if plain or len(targets) != 1:
                raise SelectError(f"{fn.sig.name}: every return must tail-call the same BLOCK")
            self.adopted = tails[0].value.sig
            if self.adopted.inline_count != fn.sig.inline_count:
                raise SelectError(
                    f"{fn.sig.name}: takes {fn.sig.inline_count} inline word(s) but tail-calls "
                    f"{self.adopted.name}, which returns past {self.adopted.inline_count}")
        elif fn.sig.inline_count:
            if not any(map(inline.is_byname_read, inline.iter_nodes(fn.body))):
                raise SelectError(f"{fn.sig.name}: a BYNAME or INLINE parameter that is never read")
            fn = inline.place_args(fn)
        body = fn.body
        if not _ends_in_transfer(body):
            if fn.sig.returns != "void":
                raise SelectError(f"{fn.sig.name}: control reaches the end of a value-returning function")
            body = ir.Block(body.stmts + (ir.Return(None),))
        plain = [r for r in _returns(body) if r not in tails and r not in jumps]
        self.last_return = plain[-1] if plain else None    # owns the exit cell
        self.final = _final_stmt(body)      # only a tail call here may fall through
        self.body = body

        self.switch_tables = _homed_switches(body)
        start = self.namer.counter
        for _ in range(MAX_PASSES):
            self.namer.counter = start
            self.label_out, self.byname_cell_done, self.fell_through = {}, False, False
            self.strides_out = {}
            items = self.header()
            body_items, end = self.stmt(body, self.entry_state())
            if end is not None:
                raise SelectError(f"{fn.sig.name}: control reaches the end of the function")
            items += body_items
            if self.label_out == self.label_prev and self.strides_out == self.strides_prev:
                break
            self.label_prev = dict(self.label_out)
            self.strides_prev = dict(self.strides_out)
        else:
            raise SelectError(f"{fn.sig.name}: label states did not converge")
        if fn.sig.conv is ir.Conv.XCT:
            return self.xct_body(items)
        return items

    def xct_body(self, items: list[ir.Item]) -> list[ir.Item]:
        """An XCT function is executed in place by `xct f`: it is one word."""
        words = [i for i in items if isinstance(i, ir.Word)]
        if len(words) != 1 or any(isinstance(i, ir.LabelDef) and i.name != self.sig.sym for i in items):
            raise SelectError(f"{self.sig.name}: an XCT function must lower to exactly one word, "
                              f"not {len(words)}")
        return [ir.LabelDef(self.sig.sym), replace(words[0], via=words[0].via + (check("XCT-BODY"),))]

    def forward(self, target: ir.Call) -> list[ir.Item]:
        """`return g(...)` as a JSP function's whole body: AC still holds the
        caller's return address, so jumping to g makes g return to that caller."""
        items: list[ir.Item] = [ir.LabelDef(self.sig.sym)]
        st = self.entry_state()
        for p, arg in zip(target.sig.params, target.args):
            if not (isinstance(arg, ir.Var) and isinstance(arg.storage, ir.Io)):
                raise SelectError(f"{self.sig.name}: forward {target.sig.name}'s {p.name} in IO")
            self.need_io(arg, st)
        return items + [W("jmp", "JSP-FORWARD", ir.Sym(target.sig.sym))]

    def header(self) -> list[ir.Item]:
        items: list[ir.Item] = [ir.LabelDef(self.sig.sym)]
        if self.sig.conv is ir.Conv.JDA:
            exit_sym = (self.adopted or self.sig).exit_sym
            items += [W(None, "JDA-ENTRY", ir.Num(0), note="entry word = parameter"),
                      W("dap", "JDA-PROLOGUE", ir.Sym(exit_sym),
                        via=("LAY-ADOPT",) if self.adopted else ())]
        elif self.sig.conv is ir.Conv.JSP:
            exit_sym = (self.adopted or self.sig).exit_sym
            items.append(W("dap", "JSP-PROLOGUE", ir.Sym(exit_sym),
                           via=("LAY-ADOPT",) if self.adopted else ()))
        return items

    def entry_state(self) -> State:
        ac = frozenset(Local(p.name) for p in self.fn.params if isinstance(p.storage, ir.Acc))
        io = frozenset(Local(p.name) for p in self.fn.params if isinstance(p.storage, ir.Io))
        return State(ac if self.sig.conv in (ir.Conv.BLOCK, ir.Conv.XCT) else frozenset(), io)

    # ----------------------------------------------------------- statements
    def stmt(self, s: ir.Stmt, st: State | None) -> tuple[list[ir.Item], State | None]:
        if st is None and not isinstance(s, (ir.Labeled, ir.Block, ir.PlaceHere)):
            raise SelectError(f"unreachable statement {s}")
        match s:
            case ir.Block():
                out: list[ir.Item] = []
                cur = st
                for sub in s.stmts:
                    items, cur = self.stmt(sub, cur)
                    out += items
                return out, cur
            case ir.Labeled():
                into = meet(meet(st, self.label_prev.get(s.label)), self.label_out.get(s.label))
                items, end = self.stmt(s.stmt, into if into is not None else State())
                return [ir.LabelDef(s.label)] + items, end
            case ir.Goto():
                self.label_out[s.label] = meet(self.label_out.get(s.label), st)
                return [W("jmp", "GOTO", ir.Sym(s.label))], None
            case ir.Assign():
                return self.assign(s.target, s.value, st)
            case ir.AssignPair():
                items, st = self.to_ac(s.value, st)
                return items, State(frozenset({fact(s.hi)}), frozenset({fact(s.lo)}))
            case ir.Eval(expr=ir.PreInc(target=ir.Deref() as d)):
                return [self.through(d, "idx", "EX-INC")], self.after_store_through(st)
            case ir.Eval(expr=ir.PreInc(target=t)):
                return [W("idx", "EX-INC", cell(t), via=_via(t))], self.after_idx(t, st)
            case ir.Eval(expr=ir.Flag(op=op, n=n)):
                return [W(op, "EX-FLAG", ir.Num(n))], st
            case ir.StoreNext():
                return self.store_next(s, st)
            case ir.AssignAddr(target=ir.Var(storage=ir.Homed(sym=sym))) if sym in self.switch_tables:
                return self.store_case(s, st)
            case ir.AssignAddr():
                if address_fact(s.value) in st.ac:
                    items = []
                elif isinstance(s.value, ir.Var) and isinstance(s.value.storage, ir.Homed):
                    items, st = self.to_ac(ir.HomeWord(s.value, self.home_op(s.value), False), st)
                else:
                    items, st = self.to_ac(s.value, st)
                return items + [W("dap", "EX-STORE-ADDR", cell(s.target), via=_via(s.target))], \
                    st.write_mem(fact(s.target))
            case ir.HomedSwitch():
                return self.homed_switch(s, st)
            case ir.OprCombine():
                return self.opr_combine(s, st)
            case ir.Eval(expr=ir.Dpy() | ir.DpyNowait() as d):
                return self.dpy(d, st)
            case ir.Switch():
                return self.switch(s, st)
            case ir.PlaceHere():
                return self.place_here(s, st)
            case ir.Eval(expr=ir.PairShift() | ir.PairStep() as p):
                return self.pair_op(p, st)
            case ir.Eval(expr=ir.Call() as c):
                return self.call(c, st)
            case ir.Eval(expr=ir.Hw(name=name)):
                return [hardware_word(name)], hardware_after(name, st)
            case ir.If():
                return self.if_(s, st)
            case ir.Forever():
                return self.forever(s, st)
            case ir.Unroll():
                return self.unroll(s, st)
            case ir.Continue():
                if not self.loops:
                    raise SelectError("continue outside a loop")
                loop = self.loops[-1]
                loop.continues.append(st)
                return [W("jmp", "CONTINUE", ir.Sym(loop.top))], None
            case ir.Return():
                return self.return_(s, st)
            case ir.SkipReturn():
                return [W("idx", "SKIP-RETURN", self.exit_cell())], State(frozenset(), st.io)
            case ir.ArgsDone():
                return [W("idx", "ARGS", self.exit_cell())], State(frozenset(), st.io)
        raise SelectError(f"no rule for statement {s}")

    @staticmethod
    def through(d: ir.Deref, op: str, rule: str) -> ir.Word:
        """op on the word d's pointer points to: the pointer's cell, indirect."""
        return W(op, rule, cell(d.pointer), i=True, via=_via_deref(d))

    @staticmethod
    def after_store_through(st: State, ac: frozenset | None = None) -> State:
        """A store through a pointer can change any word: keep register facts only."""
        st = st.without_memory()
        return State(st.ac if ac is None else ac, st.io)

    def store_through(self, d: ir.Deref, value: ir.Expr, st: State):
        """*p = e: dzm i p for 0, dio i p from a register local, else e; dac i p."""
        if value == ir.Const(0):
            return [self.through(d, "dzm", "EX-STORE-ZERO")], self.after_store_through(st)
        if isinstance(value, ir.Var) and isinstance(value.storage, ir.Io):
            self.need_io(value, st)
            return [self.through(d, "dio", "EX-STORE-IO")], self.after_store_through(st)
        items, st = self.to_ac(value, st)
        return items + [self.through(d, "dac", "EX-STORE")], self.after_store_through(st)

    def xct(self, x: ir.Xct, st: State):
        """The argument into AC (and IO), then the instruction run: `xct (w`
        for a constant, the home `p, xct .` of a HOMED pointer p, or the
        HOMED insn itself, run where it stands."""
        items, st = self.to_ac(x.hi, st)
        if x.lo is not None:
            self.need_io(x.lo, st)
        match x.insn:
            case ir.Insn(op=op) as w:
                if x.lo is None and op in PAIR_OR_IO_SHIFTS:
                    raise SelectError(f"xct of `{op}` changes IO: write xct(w, hi, lo)")
                items.append(W("xct", "EX-XCT", ir.Lit(w), via=_via_operand(w)))
            case ir.HomeLoad(pointer=p):
                items += [ir.LabelDef(p.storage.sym),
                          W("xct", "HOMED-HOME", home_address(p), via=("EX-XCT",) + _via(p))]
            case ir.Var(storage=ir.Slot(sym=sym, init=init)):
                items += [ir.LabelDef(sym),
                          W(None, "ST-SLOT", init, via=("EX-XCT",) + _via_operand(init),
                            note="run in place")]
        return items, State(frozenset(), st.io if x.lo is None else frozenset())

    @staticmethod
    def after_idx(t: ir.Var, st: State) -> State:
        ac = {fact(t)} | ({PointerBits(t.storage.sym)} if isinstance(t.storage, ir.Homed) else set())
        return State(frozenset(ac), st.io - {fact(t)})

    def home_op(self, p: ir.Var) -> str:
        if p.storage.sym not in self.home_ops:
            raise SelectError(f"{p.name} has no home: read through it with *home({p.name})")
        return self.home_ops[p.storage.sym]

    def opr_combine(self, s: ir.OprCombine, st: State):
        words, writes, vias = [], {}, []
        for part in s.parts:
            items, st = self.stmt(part, st)
            ws = [i for i in items if isinstance(i, ir.Word)]
            if len(ws) != 1 or len(ws) != len(items) or ws[0].op not in OPR_WRITES:
                raise SelectError("each part of a comma statement must be one operate-group "
                                  f"instruction ({', '.join(OPR_WRITES)}), not {items}")
            what = OPR_WRITES[ws[0].op]
            if what in writes:
                raise SelectError(f"{writes[what]} and {ws[0].op} both write {what}: the result "
                                  "would depend on the hardware's order; write two statements")
            writes[what] = ws[0].op
            words.append(ws[0])
            vias += [ws[0].rule, *ws[0].via]
        text = " ".join(emit.word_text(w) for w in words) + "-opr" * (len(words) - 1)
        return [W(text, "OPR-COMBINE", via=tuple(dict.fromkeys(vias)))], st

    def dpy(self, d: ir.Dpy | ir.DpyNowait, st: State):
        items, st = self.to_ac(d.x, st)
        self.need_io(d.y, st)
        if isinstance(d, ir.DpyNowait):
            text = ir.DPY_NOWAIT
        else:
            text = "dpy-i" + (f"+{d.intensity << 6:o}" if d.intensity else "")
        return items + [W(text, "EX-DPY", note="plot (AC, IO)")], st

    def homed_switch(self, s: ir.HomedSwitch, st: State):
        index = s.index.storage.sym
        items: list[ir.Item] = [ir.LabelDef(index),
                                W("jmp", "SWITCH-HOMED", ir.Here(), note="into the case stored here"),
                                ir.LabelDef(s.table)]
        cur, sizes = st, []
        for n, case in enumerate(s.cases):
            words, cur = self.stmt(case, meet(cur, st) if n else st)
            if cur is None:
                raise SelectError(f"case {n} of the switch on {s.index.name} must fall into case {n + 1}")
            sizes.append(sum(isinstance(w, ir.Word) for w in words))
            items += words
        if len(set(sizes)) != 1 or sizes[0] & (sizes[0] - 1):
            raise SelectError(f"the cases before the last of the switch on {s.index.name} must "
                              f"all be one power of two of words long, not {sizes}")
        self.strides_out[index] = sizes[0]
        last, end = self.stmt(s.last, meet(cur, st))
        return items + last, end

    def store_case(self, s: ir.AssignAddr, st: State):
        index = s.target.storage.sym
        items, st = self.to_ac(s.value, st)
        stride = self.strides_prev.get(index, 1)
        shift = stride.bit_length() - 1
        if shift:
            items += [W("sal", "SWITCH-HOMED", ir.ShiftCount(n)) for n in shift_chunks(shift)]
        items += [W("add", "SWITCH-HOMED", ir.Lit(ir.Sym(self.switch_tables[index]))),
                  W("dap", "SWITCH-HOMED", ir.Sym(index), via=("ST-HOMED",))]
        return items, State(frozenset(), st.io).write_mem(Cell(index))

    def inline_call(self, c: ir.Call, st: State) -> tuple[list[ir.Item], State]:
        fn = self.inlines[c.sig.name]
        items: list[ir.Item] = []
        ac, io = set(), set()
        for p, var, arg in zip(c.sig.params, fn.params, c.args):
            if p.kind is ir.ParamKind.AC:
                more, st = self.to_ac(arg, st)
                items += more
                ac.add(fact(var))
            else:
                if not (isinstance(arg, ir.Var) and isinstance(arg.storage, ir.Io)):
                    raise SelectError(f"{c.sig.name}: pass a register local for {p.name}")
                self.need_io(arg, st)
                io.add(fact(var))
        entry = State(_into_inline(st.ac) | ac, _into_inline(st.io) | io)
        body = _rename_labels(fn.body, self.namer)
        if not _ends_in_transfer(body):
            if c.sig.returns != "void":
                raise SelectError(f"{c.sig.name}: control reaches the end of a value-returning function")
            body = ir.Block(body.stmts + (ir.Return(None),))
        inst = _Instance(c.sig, _final_stmt(body), self.label())
        self.instances.append(inst)
        words, end = self.stmt(body, entry)
        self.instances.pop()
        out = end
        for e in inst.exits:
            out = meet(out, e)
        if out is None:
            raise SelectError(f"{c.sig.name}: never returns")
        copy = ir.Copy(ir.InlineBody(c.sig.name), inst.after)
        words = [replace(w, via=w.via + ("INLINE-CALL",), copies=(copy, *w.copies))
                 if isinstance(w, ir.Word) else w for w in words]
        if inst.exits:
            words.append(ir.LabelDef(inst.after))
        return items + words, State(_out_of_inline(out.ac), _out_of_inline(out.io))

    def store_next(self, s: ir.StoreNext, st: State):
        """*p++ = e: e from AC (dac i p) or from a register local (dio i p), then idx p."""
        v = s.value
        if isinstance(v, ir.Var) and isinstance(v.storage, ir.Io):
            self.need_io(v, st)
            store = W("dio", "EX-POSTINC-STORE", mem(s.pointer), i=True, via=_via(s.pointer))
            items = []
        else:
            items, st = self.to_ac(v, st)
            store = W("dac", "EX-POSTINC-STORE", mem(s.pointer), i=True, via=_via(s.pointer))
        step = W("idx", "EX-POSTINC-STORE", mem(s.pointer), via=_via(s.pointer))
        st = st.without_memory()
        return items + [store, step], State(frozenset({fact(s.pointer)}), st.io)

    def switch(self, s: ir.Switch, st: State):
        """add (T; dap J; J, jmp .; T: one word per case. A goto case is its
        jump, an empty case is `opr` (it falls into the next slot), and the
        last case's statements sit in its slot."""
        items, st = self.to_ac(s.value, st)
        table, jump = self.label(), self.label()
        items += [W("add", "SWITCH", ir.Lit(ir.Sym(table))), W("dap", "SWITCH", ir.Sym(jump)),
                  ir.LabelDef(jump), W("jmp", "SWITCH", ir.Here(), note="indexed jump"),
                  ir.LabelDef(table)]
        entered = State(frozenset(), st.io)
        for n, slot in enumerate(s.slots):
            if slot is None:
                items.append(W("opr", "SWITCH", note=f"case {n}: falls into case {n + 1}"))
                continue
            words, _ = self.stmt(slot, entered)
            items += [replace(w, rule=check("SWITCH"), note=f"case {n}") for w in words]
        last, end = self.stmt(s.last, entered)
        return items + last, end

    def place_here(self, s: ir.PlaceHere, st: State | None):
        if st is not None:
            raise SelectError("control reaches PLACE: the words laid out there would run "
                              "as instructions")
        items: list[ir.Item] = []
        for d in s.data:
            items += datum_words(d, via=("LAY-PLACE",))
        return items, None

    def exit_cell(self) -> ir.Sym:
        return ir.Sym((self.adopted or self.sig).exit_sym)

    def assign(self, t: ir.Var | ir.Deref, value: ir.Expr, st: State):
        if isinstance(t, ir.Deref):
            return self.store_through(t, value, st)
        match t.storage:
            case ir.Acc():
                items, st = self.to_ac(value, st)
                return items, State(st.ac | {fact(t)}, st.io)
            case ir.Io():
                return self.assign_io(t, value, st)
            case ir.Homed():
                raise SelectError(f"{t.name} is HOMED: assigning it stores an address (dap)")
        k = fact(t)
        if isinstance(value, ir.Var) and isinstance(value.storage, ir.Memory) and fact(value) == k:
            return [], st                       # the same cell under another name
        if value == ir.Const(0):
            return [W("dzm", "EX-STORE-ZERO", mem(t), via=_via(t))], st.write_mem(k)
        if isinstance(value, ir.Var) and isinstance(value.storage, ir.Io):
            self.need_io(value, st)
            st = st.write_mem(k)
            return [W("dio", "EX-STORE-IO", mem(t), via=_via(t))], State(st.ac, st.io | {k})
        items, st = self.to_ac(value, st)
        st = st.write_mem(k)
        return items + [W("dac", "EX-STORE", mem(t), via=_via(t))], State(st.ac | {k}, st.io)

    def assign_io(self, t: ir.Var, value: ir.Expr, st: State):
        kt = fact(t)
        match value:
            case ir.Var(storage=ir.Io()):
                self.need_io(value, st)
                return [], State(st.ac, st.io | {kt})
            case ir.Var() if isinstance(value.storage, ir.Memory):
                if fact(value) in st.io:
                    return [], State(st.ac - {kt}, st.io | {kt})
                return ([W("lio", "EX-LOAD-IO", mem(value), via=_via(value))],
                        State(st.ac - {kt}, frozenset({kt, fact(value)})))
            case ir.Const(value=0):
                return [W("cli", "EX-CONST-IO")], State(st.ac - {kt}, frozenset({kt}))
            case ir.Const(value=c):
                return [W("lio", "EX-CONST-IO", ir.Lit(ir.Num(c)))], State(st.ac - {kt}, frozenset({kt}))
            case ir.Insn():
                return [W("lio", "EX-CONST-IO", ir.Lit(value), via=_via_operand(value))], \
                    State(st.ac - {kt}, frozenset({kt}))
            case ir.HomeLoad(pointer=p):
                return [ir.LabelDef(p.storage.sym), W("lio", "HOMED-HOME", home_address(p), via=_via(p))], \
                    State(st.ac - {kt}, frozenset({kt}))
            case ir.Deref() as d:
                return [self.through(d, "lio", "EX-LOAD-IO")], State(st.ac - {kt}, frozenset({kt}))
            case ir.Shift(op=op, operand=v) if v == t:
                self.need_io(v, st)
                words = [W(IO_SHIFT_MNEMONIC[op], "EX-SHIFT", ir.ShiftCount(n)) for n in shift_chunks(value.count)]
                return words, State(st.ac, frozenset({kt}))
            case ir.Hw(name="tyi"):
                return [W("tyi", "EX-HW")], State(st.ac - {kt}, frozenset({kt}))
            case ir.Rot(op=op, operand=v) if op in ir.IO_ROTATES:
                if v != t:
                    raise SelectError(f"{op} rotates IO in place: write {t.name} = {op}({t.name}, n)")
                self.need_io(v, st)
                words = [W(op, "EX-ROT", ir.ShiftCount(n)) for n in shift_chunks(value.count)]
                return words, State(st.ac, frozenset({kt}))
        items, st = self.to_ac(value, st)
        return items + swap(), State(frozenset(), frozenset({kt}))

    def need_io(self, v: ir.Var, st: State) -> None:
        if fact(v) not in st.io:
            raise SelectError(f"register local {v.name} no longer holds its value in IO")

    def pair_op(self, p: ir.PairShift | ir.PairStep, st: State):
        if not isinstance(p.hi.storage, ir.Acc) or fact(p.hi) not in st.ac:
            raise SelectError(f"{p.op}: {p.hi.name} must be an AC local holding its value")
        if not isinstance(p.lo.storage, ir.Io) or fact(p.lo) not in st.io:
            raise SelectError(f"{p.op}: {p.lo.name} must be a register local holding its value")
        if isinstance(p, ir.PairStep):
            words = [W(p.op, "EX-STEP", self.memory_operand(p.operand))]
        else:
            words = [W(p.op, "EX-ROT", ir.ShiftCount(n)) for n in shift_chunks(p.count)]
        return words, State(frozenset({fact(p.hi)}), frozenset({fact(p.lo)}))

    def if_(self, s: ir.If, st: State):
        c = s.cond
        operand = None
        if isinstance(c, ir.FlagTest):
            pre, after, table = [], st, ("SKIP-FLAG",)
            skip_c = skips.flag_skip_when(c.n, c.negated)
            skip_not_c = skips.flag_skip_when(c.n, not c.negated)
            what = ("!" if c.negated else "") + f"flag({c.n})"
        elif isinstance(c, ir.SenseTest):
            pre, after, table = [], st, ("SKIP-SENSE",)
            skip_c = skips.sense_skip_when(c.n, c.negated)
            skip_not_c = skips.sense_skip_when(c.n, not c.negated)
            what = ("!" if c.negated else "") + f"sense({c.n})"
        elif c.against is not None:
            pre, after = self.to_ac(c.operand, st)
            if isinstance(c.against, ir.Deref):
                raise SelectError("compare with *p: load it first")
            operand = self.memory_operand(c.against)
            table = ("SKIP-SAME",) + _via_operand(c.against)
            skip_c = skips.same_skip_when(c.op)
            skip_not_c = skips.same_skip_when(skips.NEGATE[c.op])
            what = f"AC {c.op} the word"
        elif isinstance(c.operand, ir.PreInc):
            t = c.operand.target
            pre: list[ir.Item] = []
            table = ()
            if isinstance(t, ir.Deref):
                after = self.after_store_through(st, frozenset())
            else:
                after = State(frozenset({fact(t)}), st.io - {fact(t)})
            skip_c = skips.isp_skip_when(c.op)
            skip_not_c = skips.isp_skip_when(skips.NEGATE[c.op])
        elif isinstance(c.operand, ir.Var) and isinstance(c.operand.storage, ir.Io):
            self.need_io(c.operand, st)
            pre, after, table = [], st, ("SKIP-IO",)
            skip_c = skips.io_skip_when(c.op)
            skip_not_c = skips.io_skip_when(skips.NEGATE[c.op])
        else:
            pre, after = self.to_ac(c.operand, st)
            table = ()
            skip_c = skips.ac_skip_when(c.op)
            skip_not_c = skips.ac_skip_when(skips.NEGATE[c.op])

        if isinstance(c, ir.Compare) and c.against is None:
            what = f"{c.op} 0"

        def skip_word(op: str, rule: str) -> ir.Word:
            if op == "isp" and isinstance(t, ir.Deref):
                return replace(self.through(t, "isp", rule), note=f"++*{t.pointer.name} {c.op} 0")
            if op == "isp":
                return W("isp", rule, mem(t), note=f"++{t.name} {c.op} 0", via=_via(t))
            return W(op, rule, operand, note=what, via=table)

        then_items, then_end = self.stmt(s.then, after)
        single = (s.orelse is None and skip_not_c is not None
                  and sum(isinstance(i, ir.Word) for i in then_items) == 1)
        if single:
            return pre + [skip_word(skip_not_c, "IF-SINGLE")] + then_items, meet(after, then_end)
        if skip_c is None:
            raise SelectError(f"no skip for `{c.op} 0` here; rewrite the condition")
        l_else = self.label()
        out = pre + [skip_word(skip_c, "IF-MULTI"), W("jmp", "IF-MULTI", ir.Sym(l_else))] + then_items
        if s.orelse is None:
            return out + [ir.LabelDef(l_else)], meet(after, then_end)
        l_end = self.label()
        else_items, else_end = self.stmt(s.orelse, after)
        if then_end is not None:
            out.append(W("jmp", "IF-MULTI", ir.Sym(l_end)))
        out += [ir.LabelDef(l_else)] + else_items + [ir.LabelDef(l_end)]
        return out, meet(then_end, else_end)

    def forever(self, s: ir.Forever, st: State):
        top = self.label()
        start = self.namer.counter
        saved = (self.byname_cell_done, dict(self.label_out))
        assumed = st
        while True:
            self.namer.counter = start
            self.byname_cell_done, self.label_out = saved[0], dict(saved[1])
            loop = _Loop(top)
            self.loops.append(loop)
            items, end = self.stmt(s.body, assumed)
            self.loops.pop()
            head = assumed
            for back in loop.continues + [end]:
                head = meet(head, back) if back is not None else head
            head = meet(st, head)
            if head == assumed:
                break
            assumed = head
        tail = [W("jmp", "FOR-EVER", ir.Sym(top))] if end is not None else []
        return [ir.LabelDef(top)] + items + tail, None

    def unroll(self, s: ir.Unroll, st: State):
        out: list[ir.Item] = []
        for n in range(s.count):
            items, st = self.stmt(s.body, st)
            if any(isinstance(i, ir.LabelDef) for i in items):
                raise SelectError("an unrolled body cannot hold labels")
            copy = ir.Copy(ir.UnrolledBody(s.at), str(n))
            out += [replace(w, via=w.via + ("LOOP-UNROLL",), copies=(copy, *w.copies)) for w in items]
        return out, st

    def return_(self, s: ir.Return, st: State):
        if self.instances:
            return self.instance_return(s, st)
        if isinstance(s.value, ir.Call) and s.value.sig.conv is ir.Conv.BLOCK:
            return self.tail_call(s.value, st, s is self.final)
        if isinstance(s.value, ir.IndirectCall):
            return self.indirect_tail_call(s.value, st)
        items, st = self.return_value(s, st)
        if self.sig.conv is ir.Conv.XCT:
            return items, None
        if self.sig.byname:
            return items + [W("jmp", "RET-INDIRECT", self.exit_cell(), i=True)], None
        if s is self.last_return:
            return items + [ir.LabelDef(self.sig.exit_sym), W("jmp", "LAY-EXIT", ir.Here())], None
        return items + [W("jmp", "RET", ir.Sym(self.sig.exit_sym))], None

    def instance_return(self, s: ir.Return, st: State):
        inst = self.instances[-1]
        if isinstance(s.value, ir.IndirectCall) or \
                (isinstance(s.value, ir.Call) and s.value.sig.conv is ir.Conv.BLOCK):
            raise SelectError(f"{inst.sig.name}: a static inline function cannot tail-call")
        items, st = self.return_value(s, st)
        if s is inst.final:
            return items, st
        inst.exits.append(st)
        return items + [W("jmp", "INLINE-RETURN", ir.Sym(inst.after))], None

    def return_value(self, s: ir.Return, st: State):
        items: list[ir.Item] = []
        if isinstance(s.value, ir.Pair):
            items, st = self.to_ac(s.value.hi, st)
            lo = s.value.lo
            if isinstance(lo, ir.Var) and isinstance(lo.storage, ir.Io):
                self.need_io(lo, st)
            elif isinstance(lo, ir.Var) and isinstance(lo.storage, ir.Memory):
                items.append(W("lio", "EX-LOAD-IO", mem(lo), via=_via(lo)))
            else:
                raise SelectError("the low half of a returned dword must be a register local or memory")
        elif s.value is not None:
            items, st = self.to_ac(s.value, st)
        return items, st

    def indirect_tail_call(self, c: ir.IndirectCall, st: State):
        """return p(...): the arguments, then a jump through p."""
        if c.sig.conv is not ir.Conv.BLOCK:
            raise SelectError(f"a tail call through {c.pointer.name} needs a BLOCK function type")
        items, _ = self.block_args(c.sig, c.args, st)
        return items + [W("jmp", "TAIL-CALL-INDIRECT", mem(c.pointer), i=True)], None

    def block_args(self, sig: ir.Signature, args, st: State):
        items: list[ir.Item] = []
        for p, arg in zip(sig.params, args):
            if p.kind is ir.ParamKind.AC:
                more, st = self.to_ac(arg, st)
                items += more
            elif p.kind is ir.ParamKind.IO:
                if not (isinstance(arg, ir.Var) and isinstance(arg.storage, ir.Io)):
                    raise SelectError(f"{sig.name}: pass a register local for {p.name}")
                self.need_io(arg, st)
            elif not (isinstance(arg, ir.Var) and isinstance(arg.storage, ir.ByName)):
                raise SelectError(f"{sig.name}: a BLOCK's BYNAME parameter is the caller's own")
        return items, st

    def tail_call(self, c: ir.Call, st: State, final: bool):
        items, _ = self.block_args(c.sig, c.args, st)
        if final and self.next_sym == c.sig.sym:
            self.fell_through = True
            return items, None
        return items + [W("jmp", "TAIL-CALL", ir.Sym(c.sig.sym))], None

    def call(self, c: ir.Call, st: State) -> tuple[list[ir.Item], State]:
        """A JDA, JSP or XCT call: AC argument, the call word, then for JDA one
        inline word per BYNAME argument."""
        if c.sig.conv is ir.Conv.BLOCK:
            raise SelectError(f"{c.sig.name} is a BLOCK: only `return {c.sig.name}(...)` enters it")
        if c.sig.conv is ir.Conv.INLINE:
            return self.inline_call(c, st)
        items: list[ir.Item] = []
        args = dict(zip((p.kind for p in c.sig.params), c.args))
        if ir.ParamKind.AC in args:
            items, st = self.to_ac(args[ir.ParamKind.AC], st)
        if ir.ParamKind.IO in args:
            arg = args[ir.ParamKind.IO]
            if not (isinstance(arg, ir.Var) and isinstance(arg.storage, ir.Io)):
                raise SelectError(f"{c.sig.name}: pass a register local as the IO argument")
            self.need_io(arg, st)
        op, rule = {ir.Conv.JDA: ("jda", "JDA-CALL"), ir.Conv.JSP: ("jsp", "JSP-CALL"),
                    ir.Conv.XCT: ("xct", "XCT-CALL")}[c.sig.conv]
        items.append(W(op, rule, ir.Sym(c.sig.sym)))
        for p, arg in zip(c.sig.params, c.args):
            if p.kind is ir.ParamKind.BYNAME:
                via = _via(arg) if isinstance(arg, ir.Var) else ()
                items.append(W("lac", "JDA-BYNAME-ARG", self.memory_operand(arg), via=via))
            elif p.kind is ir.ParamKind.INLINE:
                items.append(W(None, "JDA-INLINE-ARG", self.inline_word(arg)))
        if self.keeps_io.get(c.sig.sym):
            return items, State(frozenset(), st.without_memory().io)
        return items, State()

    @staticmethod
    def inline_word(e: ir.Expr) -> ir.Operand:
        """The word after the call for an INLINE argument: a constant or an address."""
        match e:
            case ir.Const(value=v):
                return ir.Num(v)
            case ir.AddrOf(operand=o):
                return o
            case ir.CodeRef(sig=sig):
                return ir.Sym(sig.sym)
        raise SelectError(f"an INLINE argument is a constant, an array or a function, not {e}")

    # ---------------------------------------------------------- expressions
    def to_ac(self, e: ir.Expr, st: State) -> tuple[list[ir.Item], State]:
        """Words that leave e's value in AC, and the state after them."""
        match e:
            case ir.Var(storage=ir.Acc()):
                if fact(e) not in st.ac:
                    raise SelectError(f"AC local {e.name} was clobbered before this use; "
                                      "name a static to hold it")
                return [], st
            case ir.Var(storage=ir.Io()):
                self.need_io(e, st)
                return swap(), State()
            case ir.Var(storage=ir.ByName()):
                return self.byname_read(), State(frozenset(), st.io)
            case ir.Var(storage=ir.Inline()):
                return [W("lac", "INLINE-READ", self.exit_cell(), i=True)], State(frozenset(), st.io)
            case ir.Var(storage=ir.Homed()):
                raise SelectError(f"{e.name} is HOMED: its value is the address field of an "
                                  "instruction; read through it with *home(...)")
            case ir.Insn():
                return [W("lac", "EX-CONST-AC", ir.Lit(e), via=_via_operand(e))], \
                    State(frozenset({address_fact(e)} - {None}), st.io)
            case ir.AddrOf(operand=o):
                return [W("law", "EX-CODE", o, via=("ST-POOL",) if o.pool else ())], \
                    State(frozenset({address_fact(e)}), st.io)
            case ir.HomeWord(pointer=p, op=op, increment=inc):
                if op != self.home_op(p):
                    raise SelectError(f"{p.name}'s home is `{self.home_op(p)} .`, not `{op}`")
                if inc:
                    return [W("idx", "HOMED-WORD", cell(p), via=_via(p))], self.after_idx(p, st)
                if fact(p) in st.ac:
                    return [], st
                return [W("lac", "HOMED-WORD", cell(p), via=_via(p))], \
                    State(frozenset({fact(p), PointerBits(p.storage.sym)}), st.io)
            case ir.HomeLoad(pointer=p):
                return [ir.LabelDef(p.storage.sym), W("lac", "HOMED-HOME", home_address(p), via=_via(p))], \
                    State(frozenset(), st.io)
            case ir.Var():
                if fact(e) in st.ac:
                    return [], st
                return [W("lac", "EX-LOAD", mem(e), via=_via(e))], State(frozenset({fact(e)}), st.io)
            case ir.Const(value=v):
                return [self.const_ac(v)], State(frozenset(), st.io)
            case ir.Deref() as d:
                return [self.through(d, "lac", "EX-LOAD")], State(frozenset(), st.io)
            case ir.PreInc(target=ir.Deref() as d):
                return [self.through(d, "idx", "EX-INC")], self.after_store_through(st, frozenset())
            case ir.Xct():
                return self.xct(e, st)
            case ir.PreInc(target=t):
                return [W("idx", "EX-INC", cell(t), via=_via(t))], self.after_idx(t, st)
            case ir.Neg():
                items, st = self.to_ac(e.operand, st)
                return items + [W("cma", "EX-UNARY")], State(frozenset(), st.io)
            case ir.Binary():
                items, st = self.to_ac(e.left, st)
                via = _via_operand(e.right)
                if isinstance(e.right, ir.Deref):
                    return items + [W(BIN_MNEMONIC[e.op], "EX-BIN", cell(e.right.pointer), i=True,
                                      via=via)], State(frozenset(), st.io)
                operand = self.memory_operand(e.right)
                return items + [W(BIN_MNEMONIC[e.op], "EX-BIN", operand, via=via)], \
                    State(frozenset(), st.io)
            case ir.Shift():
                items, st = self.to_ac(e.operand, st)
                words = [W(SHIFT_MNEMONIC[e.op], "EX-SHIFT", ir.ShiftCount(n))
                         for n in shift_chunks(e.count)]
                return items + words, State(frozenset(), st.io)
            case ir.Rot(op=op) if op in ir.AC_ROTATES:
                items, st = self.to_ac(e.operand, st)
                words = [W(op, "EX-ROT", ir.ShiftCount(n)) for n in shift_chunks(e.count)]
                return items + words, State(frozenset(), st.io)
            case ir.Call() if e.sig.returns in ("word", "word*", "dword") and e.sig.conv is ir.Conv.INLINE:
                return self.inline_call(e, st)
            case ir.Call() if e.sig.returns in ("word", "word*", "dword"):
                return self.call(e, st)
            case ir.Half(which="hi"):
                return self.call(e.call, st)
            case ir.IndirectCall(pointer=p):
                raise SelectError(f"a call through {p.name} is a jump: write `return {p.name}(...)`")
            case ir.CodeRef(sig=sig, flags=0):
                return [W("law", "EX-CODE", ir.Sym(sig.sym))], State(frozenset(), st.io)
            case ir.CodeRef(sig=sig, flags=flags):
                return [W("lac", "EX-CODE", ir.Lit(ir.Sym(sig.sym, offset=flags)), note="address with flags")], \
                    State(frozenset(), st.io)
        raise SelectError(f"no rule puts {e} in AC")

    def byname_read(self) -> list[ir.Item]:
        """The first read is the cell R itself (`R, xct`, address patched by the
        prologue); later reads execute it (`xct R`)."""
        cell = self.exit_cell()
        if not self.byname_cell_done:
            self.byname_cell_done = True
            return [ir.LabelDef(cell.name), W("xct", "BYNAME-READ", note="the caller's inline word")]
        return [W("xct", "BYNAME-READ", cell)]

    @staticmethod
    def const_ac(v: int) -> ir.Word:
        if v == 0:
            return W("cla", "EX-CONST-AC")
        if v <= LAW_MAX:
            return W("law", "EX-CONST-AC", ir.Num(v))
        if v ^ ir.WORD_MASK <= LAW_MAX:
            return W("law", "EX-CONST-AC", ir.Num(v ^ ir.WORD_MASK), i=True)
        return W("lac", "EX-CONST-AC", ir.Lit(ir.Num(v)))

    @staticmethod
    def memory_operand(e: ir.Expr) -> ir.Operand:
        match e:
            case ir.Const(value=v):
                return ir.Lit(ir.Num(v))
            case ir.Insn():
                return ir.Lit(e)
            case ir.AddrOf(operand=o):
                return ir.Lit(o)
            case ir.Var(storage=s) if isinstance(s, ir.Memory):
                return mem(e)
        raise SelectError(f"operand {e} must be a memory operand or a constant; "
                          "name a static to hold it")


def _final_stmt(b: ir.Block) -> ir.Stmt | None:
    """The statement laid out last in a function body."""
    last: ir.Stmt | None = b
    while isinstance(last, (ir.Labeled, ir.Block)):
        if isinstance(last, ir.Block):
            if not last.stmts:
                return None
            last = last.stmts[-1]
        else:
            last = last.stmt
    return last


def hardware_after(name: str, st: State) -> State:
    """tyi reads the typewriter into IO; lsm leaves both registers alone."""
    return State(st.ac, frozenset()) if name == "tyi" else st


def _forwarded(body: ir.Block) -> ir.Call | None:
    """g(...) when the whole body is `return g(...)` for a JSP g."""
    if len(body.stmts) == 1 and isinstance(r := body.stmts[0], ir.Return) \
            and isinstance(r.value, ir.Call) and r.value.sig.conv is ir.Conv.JSP:
        return r.value
    return None


def _ends_in_transfer(b: ir.Block) -> bool:
    stmts = list(b.stmts)
    while stmts and isinstance(stmts[-1], ir.PlaceHere):    # data, laid out after the code
        stmts.pop()
    return isinstance(_final_stmt(ir.Block(tuple(stmts))), (ir.Return, ir.Forever, ir.Goto))


def _children(node) -> list:
    match node:
        case ir.Block():
            return list(node.stmts)
        case ir.If():
            return [node.then] + ([node.orelse] if node.orelse else [])
        case ir.Forever() | ir.Unroll():
            return [node.body]
        case ir.Labeled():
            return [node.stmt]
        case ir.Switch():
            return [x for x in node.slots if x is not None] + [node.last]
        case ir.HomedSwitch():
            return list(node.cases) + [node.last]
    return []


def _returns(node) -> list[ir.Return]:
    if isinstance(node, ir.Return):
        return [node]
    return [r for c in _children(node) for r in _returns(c)]


def _tail_calls(node) -> list[ir.Return]:
    return [r for r in _returns(node)
            if isinstance(r.value, ir.Call) and r.value.sig.conv is ir.Conv.BLOCK]


def hardware_word(name: str) -> ir.Word:
    if name == "ioh":           # wait for the completion pulse: iot with the wait bit
        return W("iot", "EX-HW", i=True)
    return W(name, "EX-HW")


def _homed_switches(body) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in inline.iter_nodes(body):
        if isinstance(n, ir.HomedSwitch):
            if n.index.storage.sym in out:
                raise SelectError(f"{n.index.name} indexes two switches: a HOMED word has one home")
            out[n.index.storage.sym] = n.table
    return out


def _rename_labels(body: ir.Block, namer) -> ir.Block:
    names = {n.label for n in inline.iter_nodes(body) if isinstance(n, ir.Labeled)}
    names |= {n.table for n in inline.iter_nodes(body) if isinstance(n, ir.HomedSwitch)}
    fresh = {old: namer.fresh() for old in sorted(names)}

    def walk(node):
        if isinstance(node, tuple):
            return tuple(walk(x) for x in node)
        if isinstance(node, ir.Labeled):
            return ir.Labeled(fresh[node.label], walk(node.stmt))
        if isinstance(node, ir.Goto):
            return ir.Goto(fresh.get(node.label, node.label))
        if isinstance(node, ir.HomedSwitch):
            return ir.HomedSwitch(node.index, fresh[node.table], walk(node.cases), walk(node.last))
        if is_dataclass(node) and not isinstance(node, (ir.Signature, ir.Var, ir.Datum)) \
                and isinstance(node, STMT_TYPES):
            return replace(node, **{f.name: walk(getattr(node, f.name)) for f in fields(node)})
        return node
    return walk(body)


STMT_TYPES = (ir.Block, ir.If, ir.Forever, ir.Unroll, ir.Switch, ir.OprCombine)


def home_address(p: ir.Var) -> ir.Operand:
    return p.storage.init if p.storage.init is not None else ir.Here()
