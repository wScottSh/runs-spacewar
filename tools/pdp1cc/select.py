"""IR -> Item list. Owns AC/IO value tracking (TRACK) and skip selection.

Every lowering step is a pure function (node, State) -> (items, State), so a
loop body, or a whole function with backward gotos, can be lowered again
until the states at its loop heads and labels are a fixpoint."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from . import inline, ir, skips
from .rules import check

BIN_MNEMONIC = {"+": "add", "-": "sub", "&": "and", "|": "ior", "^": "xor"}
SHIFT_MNEMONIC = {"<<": "sal", ">>": "sar"}
PAIR_SHIFTS = {"rcl", "rcr", "scl", "scr"}
PAIR_STEPS = {"mus", "dis"}
AC_ROTATES = {"ral", "rar"}
IO_ROTATES = {"ril", "rir"}
LAW_MAX = (1 << 12) - 1
SWAP_HALF = 9           # rcr 9s twice exchanges AC and IO
MAX_PASSES = 20
# Instructions that can change IO. A function whose words include none of
# these, and that leaves only through its own exit, preserves IO for its callers.
IO_WRITERS = {"lio", "cli", "tyi", "rcl", "rcr", "scl", "scr", "ril", "rir", "sil", "sir",
              "mus", "dis", "jsp", "jda", "xct"}
LEAVES_ELSEWHERE = {"TAIL-CALL", "TAIL-CALL-INDIRECT", "JSP-FORWARD", "RET-INDIRECT"}


class SelectError(Exception):
    pass


@dataclass(frozen=True)
class State:
    """Names whose current value AC / IO hold. None (as a State) = unreachable."""
    ac: frozenset[str] = frozenset()
    io: frozenset[str] = frozenset()

    def write_mem(self, key: str) -> State:
        return State(self.ac - {key}, self.io - {key})

    def registers_only(self) -> State:
        """After a store through a pointer: any memory word may have changed,
        so only facts about register locals survive."""
        return State(frozenset(k for k in self.ac if k.startswith("%")),
                     frozenset(k for k in self.io if k.startswith("%")))


def meet(a: State | None, b: State | None) -> State | None:
    if a is None:
        return b
    if b is None:
        return a
    return State(a.ac & b.ac, a.io & b.io)


def key(v: ir.Var) -> str:
    if isinstance(v.storage, ir.Memory):
        return ir.mem_sym(v.storage)
    if isinstance(v.storage, ir.Homed):
        return v.storage.sym
    return "%" + v.name


def W(op, rule, operand=None, i=False, note="", via=()):
    return ir.Word(op, check(rule), operand, i, (), note, tuple(check(r) for r in via))


def _via(v: ir.Var) -> tuple[str, ...]:
    if isinstance(v.storage, ir.Entry) and v.storage.alias:
        return ("ST-ENTRY-CELL",)
    if isinstance(v.storage, ir.Pool):
        return ("ST-POOL",)
    if isinstance(v.storage, ir.Homed):
        return ("ST-HOMED",)
    return ()


def _via_operand(e: ir.Expr) -> tuple[str, ...]:
    """Rules that chose part of a memory operand: a pool or entry-cell name,
    or an instruction constant (and a pool name inside it)."""
    if isinstance(e, ir.Var):
        return _via(e)
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
        if isinstance(v, ir.Insn):
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
class FunctionLowerer:
    fn: ir.Function
    namer: object                   # dialect.Namer: generated labels continue the unit's numbering
    next_sym: str | None = None     # symbol of the item laid out after this function
    keeps_io: dict[str, bool] = field(default_factory=dict)   # callees laid out earlier
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
        if fn.sig.conv == "jsp" and (target := _forwarded(fn.body)) is not None:
            return self.forward(target)
        tails = _tail_calls(fn.body)
        jumps = _indirect_tails(fn.body)
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
            if not _any_byname_read(fn.body):
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

        start = self.namer.counter
        for _ in range(MAX_PASSES):
            self.namer.counter = start
            self.label_out, self.byname_cell_done, self.fell_through = {}, False, False
            items = self.header()
            body_items, end = self.stmt(body, self.entry_state())
            if end is not None:
                raise SelectError(f"{fn.sig.name}: control reaches the end of the function")
            items += body_items
            if self.label_out == self.label_prev:
                break
            self.label_prev = dict(self.label_out)
        else:
            raise SelectError(f"{fn.sig.name}: label states did not converge")
        if fn.sig.conv == "xct":
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
        if self.sig.conv == "jda":
            exit_sym = (self.adopted or self.sig).exit_sym
            items += [W(None, "JDA-ENTRY", ir.Num(0), note="entry word = parameter"),
                      W("dap", "JDA-PROLOGUE", ir.Sym(exit_sym),
                        via=("LAY-ADOPT",) if self.adopted else ())]
        elif self.sig.conv == "jsp":
            exit_sym = (self.adopted or self.sig).exit_sym
            items.append(W("dap", "JSP-PROLOGUE", ir.Sym(exit_sym),
                           via=("LAY-ADOPT",) if self.adopted else ()))
        return items

    def entry_state(self) -> State:
        ac = frozenset("%" + p.name for p in self.fn.params
                       if isinstance(p.storage, ir.Acc))
        io = frozenset("%" + p.name for p in self.fn.params if isinstance(p.storage, ir.Io))
        return State(ac if self.sig.conv in ("block", "xct") else frozenset(), io)

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
                return items, State(frozenset({key(s.hi)}), frozenset({key(s.lo)}))
            case ir.Eval(expr=ir.PreInc(target=t)):
                return [W("idx", "EX-INC", cell(t), via=_via(t))], \
                    State(frozenset({key(t)}), st.io - {key(t)})
            case ir.Eval(expr=ir.Flag(op=op, n=n)):
                return [W(op, "EX-FLAG", ir.Num(n))], st
            case ir.StoreNext():
                return self.store_next(s, st)
            case ir.AssignAddr():
                items, st = self.to_ac(s.value, st)
                return items + [W("dap", "EX-STORE-ADDR", cell(s.target), via=_via(s.target))], \
                    st.write_mem(key(s.target))
            case ir.Switch():
                return self.switch(s, st)
            case ir.PlaceHere():
                return self.place_here(s, st)
            case ir.Eval(expr=ir.PairOp() as p):
                return self.pair_op(p, st)
            case ir.Eval(expr=ir.Call() as c):
                return self.call(c, st)
            case ir.Eval(expr=ir.Hw(name=name)):
                return [W(name, "EX-HW")], hardware_after(name, st)
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
        st = st.registers_only()
        return items + [store, step], State(frozenset({key(s.pointer)}), st.io)

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

    def assign(self, t: ir.Var, value: ir.Expr, st: State):
        match t.storage:
            case ir.Acc():
                items, st = self.to_ac(value, st)
                return items, State(st.ac | {key(t)}, st.io)
            case ir.Io():
                return self.assign_io(t, value, st)
            case ir.Homed():
                raise SelectError(f"{t.name} is HOMED: assigning it stores an address (dap)")
        k = key(t)
        if isinstance(value, ir.Var) and isinstance(value.storage, ir.Memory) and key(value) == k:
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
        kt = key(t)
        match value:
            case ir.Var(storage=ir.Io()):
                self.need_io(value, st)
                return [], State(st.ac, st.io | {kt})
            case ir.Var() if isinstance(value.storage, ir.Memory):
                if key(value) in st.io:
                    return [], State(st.ac - {kt}, st.io | {kt})
                return ([W("lio", "EX-LOAD-IO", mem(value), via=_via(value))],
                        State(st.ac - {kt}, frozenset({kt, key(value)})))
            case ir.Const(value=0):
                return [W("cli", "EX-CONST-IO")], State(st.ac - {kt}, frozenset({kt}))
            case ir.Const(value=c):
                return [W("lio", "EX-CONST-IO", ir.Lit(ir.Num(c)))], State(st.ac - {kt}, frozenset({kt}))
            case ir.Insn():
                return [W("lio", "EX-CONST-IO", ir.Lit(value), via=_via_operand(value))], \
                    State(st.ac - {kt}, frozenset({kt}))
            case ir.HomeLoad(pointer=p):
                return [ir.LabelDef(p.storage.sym), W("lio", "HOMED-HOME", ir.Here(), via=_via(p))], \
                    State(st.ac - {kt}, frozenset({kt}))
            case ir.Hw(name="tyi"):
                return [W("tyi", "EX-HW")], State(st.ac - {kt}, frozenset({kt}))
            case ir.Rot(op=op, operand=v) if op in IO_ROTATES:
                if v != t:
                    raise SelectError(f"{op} rotates IO in place: write {t.name} = {op}({t.name}, n)")
                self.need_io(v, st)
                words = [W(op, "EX-ROT", ir.ShiftCount(n)) for n in shift_chunks(value.count)]
                return words, State(st.ac, frozenset({kt}))
        items, st = self.to_ac(value, st)
        return items + swap(), State(frozenset(), frozenset({kt}))

    def need_io(self, v: ir.Var, st: State) -> None:
        if key(v) not in st.io:
            raise SelectError(f"register local {v.name} no longer holds its value in IO")

    def pair_op(self, p: ir.PairOp, st: State):
        if not isinstance(p.hi.storage, ir.Acc) or key(p.hi) not in st.ac:
            raise SelectError(f"{p.op}: {p.hi.name} must be an AC local holding its value")
        if not isinstance(p.lo.storage, ir.Io) or key(p.lo) not in st.io:
            raise SelectError(f"{p.op}: {p.lo.name} must be a register local holding its value")
        if p.op in PAIR_STEPS:
            words = [W(p.op, "EX-STEP", self.memory_operand(p.operand))]
        else:
            words = [W(p.op, "EX-ROT", ir.ShiftCount(n)) for n in shift_chunks(p.count)]
        return words, State(frozenset({key(p.hi)}), frozenset({key(p.lo)}))

    def if_(self, s: ir.If, st: State):
        c = s.cond
        if isinstance(c, ir.FlagTest):
            pre, after, table = [], st, ("SKIP-FLAG",)
            skip_c = skips.flag_skip_when(c.n, c.negated)
            skip_not_c = skips.flag_skip_when(c.n, not c.negated)
            what = ("!" if c.negated else "") + f"flag({c.n})"
        elif isinstance(c.operand, ir.PreInc):
            t = c.operand.target
            pre: list[ir.Item] = []
            table = ()
            after = State(frozenset({key(t)}), st.io - {key(t)})
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

        if not isinstance(c, ir.FlagTest):
            what = f"{c.op} 0"

        def skip_word(op: str, rule: str) -> ir.Word:
            if op == "isp":
                return W("isp", rule, mem(t), note=f"++{t.name} {c.op} 0", via=_via(t))
            return W(op, rule, note=what, via=table)

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
        for _ in range(s.count):
            items, st = self.stmt(s.body, st)
            if any(isinstance(i, ir.LabelDef) for i in items):
                raise SelectError("an unrolled body cannot hold labels")
            out += [replace(w, via=w.via + ("LOOP-UNROLL",)) for w in items]
        return out, st

    def return_(self, s: ir.Return, st: State):
        if isinstance(s.value, ir.Call) and s.value.sig.conv == "block":
            return self.tail_call(s.value, st, s is self.final)
        if isinstance(s.value, ir.IndirectCall):
            return self.indirect_tail_call(s.value, st)
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
        if self.sig.conv == "xct":
            return items, None
        if self.sig.byname:
            return items + [W("jmp", "RET-INDIRECT", self.exit_cell(), i=True)], None
        if s is self.last_return:
            return items + [ir.LabelDef(self.sig.exit_sym), W("jmp", "LAY-EXIT", ir.Here())], None
        return items + [W("jmp", "RET", ir.Sym(self.sig.exit_sym))], None

    def indirect_tail_call(self, c: ir.IndirectCall, st: State):
        """return p(...): the arguments, then a jump through p."""
        if c.sig.conv != "block":
            raise SelectError(f"a tail call through {c.pointer.name} needs a BLOCK function type")
        items, _ = self.block_args(c.sig, c.args, st)
        return items + [W("jmp", "TAIL-CALL-INDIRECT", mem(c.pointer), i=True)], None

    def block_args(self, sig: ir.Signature, args, st: State):
        items: list[ir.Item] = []
        for p, arg in zip(sig.params, args):
            if p.kind == "ac":
                more, st = self.to_ac(arg, st)
                items += more
            elif p.kind == "io":
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
        if c.sig.conv == "block":
            raise SelectError(f"{c.sig.name} is a BLOCK: only `return {c.sig.name}(...)` enters it")
        items: list[ir.Item] = []
        args = dict(zip((p.kind for p in c.sig.params), c.args))
        if "ac" in args:
            items, st = self.to_ac(args["ac"], st)
        if "io" in args:
            arg = args["io"]
            if not (isinstance(arg, ir.Var) and isinstance(arg.storage, ir.Io)):
                raise SelectError(f"{c.sig.name}: pass a register local as the IO argument")
            self.need_io(arg, st)
        op, rule = {"jda": ("jda", "JDA-CALL"), "jsp": ("jsp", "JSP-CALL"),
                    "xct": ("xct", "XCT-CALL")}[c.sig.conv]
        items.append(W(op, rule, ir.Sym(c.sig.sym)))
        for p, arg in zip(c.sig.params, c.args):
            if p.kind == "byname":
                via = _via(arg) if isinstance(arg, ir.Var) else ()
                items.append(W("lac", "JDA-BYNAME-ARG", self.memory_operand(arg), via=via))
            elif p.kind == "inline":
                items.append(W(None, "JDA-INLINE-ARG", self.inline_word(arg)))
        if self.keeps_io.get(c.sig.sym):
            return items, State(frozenset(), st.registers_only().io)
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
                if key(e) not in st.ac:
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
                return [W("lac", "EX-CONST-AC", ir.Lit(e), via=_via_operand(e))], State(frozenset(), st.io)
            case ir.AddrOf(operand=o):
                return [W("law", "EX-CODE", o, via=("ST-POOL",) if o.pool else ())], \
                    State(frozenset(), st.io)
            case ir.HomeLoad(pointer=p):
                return [ir.LabelDef(p.storage.sym), W("lac", "HOMED-HOME", ir.Here(), via=_via(p))], \
                    State(frozenset(), st.io)
            case ir.Var():
                if key(e) in st.ac:
                    return [], st
                return [W("lac", "EX-LOAD", mem(e), via=_via(e))], State(frozenset({key(e)}), st.io)
            case ir.Const(value=v):
                return [self.const_ac(v)], State(frozenset(), st.io)
            case ir.PreInc(target=t):
                return [W("idx", "EX-INC", mem(t))], State(frozenset({key(t)}), st.io - {key(t)})
            case ir.Neg():
                items, st = self.to_ac(e.operand, st)
                return items + [W("cma", "EX-UNARY")], State(frozenset(), st.io)
            case ir.Binary():
                items, st = self.to_ac(e.left, st)
                operand = self.memory_operand(e.right)
                via = _via_operand(e.right)
                return items + [W(BIN_MNEMONIC[e.op], "EX-BIN", operand, via=via)], \
                    State(frozenset(), st.io)
            case ir.Shift():
                items, st = self.to_ac(e.operand, st)
                words = [W(SHIFT_MNEMONIC[e.op], "EX-SHIFT", ir.ShiftCount(n))
                         for n in shift_chunks(e.count)]
                return items + words, State(frozenset(), st.io)
            case ir.Rot(op=op) if op in AC_ROTATES:
                items, st = self.to_ac(e.operand, st)
                words = [W(op, "EX-ROT", ir.ShiftCount(n)) for n in shift_chunks(e.count)]
                return items + words, State(frozenset(), st.io)
            case ir.Call() if e.sig.returns in ("word", "dword"):
                return self.call(e, st)
            case ir.Half(which="hi"):
                return self.call(e.call, st)
            case ir.IndirectCall(pointer=p):
                raise SelectError(f"a call through {p.name} is a jump: write `return {p.name}(...)`")
            case ir.CodeRef(sig=sig):
                return [W("law", "EX-CODE", ir.Sym(sig.sym))], State(frozenset(), st.io)
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
            and isinstance(r.value, ir.Call) and r.value.sig.conv == "jsp":
        return r.value
    return None


def _indirect_tails(node) -> list[ir.Return]:
    return [r for r in _returns(node) if isinstance(r.value, ir.IndirectCall)]


def _ends_in_transfer(b: ir.Block) -> bool:
    stmts = list(b.stmts)
    while stmts and isinstance(stmts[-1], ir.PlaceHere):    # data, laid out after the code
        stmts.pop()
    if not stmts:
        return False
    last = stmts[-1]
    while isinstance(last, (ir.Labeled, ir.Block)):
        if isinstance(last, ir.Block):
            if not last.stmts:
                return False
            last = last.stmts[-1]
        else:
            last = last.stmt
    return isinstance(last, (ir.Return, ir.Forever, ir.Goto))


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
    return []


def _returns(node) -> list[ir.Return]:
    if isinstance(node, ir.Return):
        return [node]
    return [r for c in _children(node) for r in _returns(c)]


def _tail_calls(node) -> list[ir.Return]:
    return [r for r in _returns(node)
            if isinstance(r.value, ir.Call) and r.value.sig.conv == "block"]


def _any_byname_read(node) -> bool:
    return any(map(inline.is_byname_read, inline.iter_nodes(node)))
