"""IR -> Item list. Owns AC/IO value tracking (TRACK) and skip selection.

Every lowering step is a pure function (node, State) -> (items, State), so a
loop body can be re-lowered until the state at its head is a fixpoint."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import ir, skips
from .rules import check

BIN_MNEMONIC = {"+": "add", "-": "sub", "&": "and", "|": "ior", "^": "xor"}
SHIFT_MNEMONIC = {"<<": "sal", ">>": "sar"}
PAIR_MNEMONIC = {"rcl": "rcl"}
LAW_MAX = (1 << 12) - 1


class SelectError(Exception):
    pass


@dataclass(frozen=True)
class State:
    """Names whose current value AC / IO hold. None (as a State) = unreachable."""
    ac: frozenset[str] = frozenset()
    io: frozenset[str] = frozenset()

    def write_mem(self, key: str) -> State:
        return State(self.ac - {key}, self.io - {key})


def meet(a: State | None, b: State | None) -> State | None:
    if a is None:
        return b
    if b is None:
        return a
    return State(a.ac & b.ac, a.io & b.io)


def key(v: ir.Var) -> str:
    if isinstance(v.storage, ir.Memory):
        return ir.mem_sym(v.storage)
    return "%" + v.name


def W(op, rule, operand=None, i=False, note=""):
    return ir.Word(op, check(rule), operand, i, (), note)


def mem(v: ir.Var) -> ir.Sym:
    if not isinstance(v.storage, ir.Memory):
        raise SelectError(f"{v.name} is a register local, not a memory operand")
    return ir.Sym(ir.mem_sym(v.storage))


def shift_chunks(n: int) -> list[int]:
    if not 0 < n < 36:
        raise SelectError(f"shift count {n} out of range")
    return [9] * (n // 9) + ([n % 9] if n % 9 else [])


@dataclass
class _Loop:
    top: str
    continues: list[State] = field(default_factory=list)


@dataclass
class FunctionLowerer:
    fn: ir.Function
    label_prefix: str
    counter: int = 0
    loops: list[_Loop] = field(default_factory=list)
    exit_label: str = ""
    last_return: ir.Return | None = None

    def label(self) -> str:
        self.counter += 1
        name = f"{self.label_prefix}{self.counter}"
        if len(name) > 6:
            raise SelectError(f"generated label {name} exceeds 6 characters")
        return name

    # ------------------------------------------------------------ function
    def lower(self) -> list[ir.Item]:
        fn = self.fn
        body = fn.body
        if not _ends_in_transfer(body):
            if fn.returns_value:
                raise SelectError(f"{fn.sym}: control reaches the end of a word function")
            body = ir.Block(body.stmts + (ir.Return(None),))
        self.last_return = _last_return(body)
        self.exit_label = self.label()
        items: list[ir.Item] = [
            ir.LabelDef(fn.sym),
            W(None, "JDA-ENTRY", ir.Num(0), note="entry word = parameter"),
            W("dap", "JDA-PROLOGUE", ir.Sym(self.exit_label)),
        ]
        body_items, end = self.stmt(body, State())
        if end is not None:
            raise SelectError(f"{fn.sym}: control reaches the end of the function")
        return items + body_items

    # ----------------------------------------------------------- statements
    def stmt(self, s: ir.Stmt, st: State) -> tuple[list[ir.Item], State | None]:
        match s:
            case ir.Block():
                out: list[ir.Item] = []
                cur: State | None = st
                for sub in s.stmts:
                    if cur is None:
                        raise SelectError(f"unreachable statement {sub}")
                    items, cur = self.stmt(sub, cur)
                    out += items
                return out, cur
            case ir.Assign():
                return self.assign(s.target, s.value, st)
            case ir.Eval(expr=ir.PreInc(target=t)):
                return [W("idx", "EX-INC", mem(t))], State(frozenset({key(t)}), st.io - {key(t)})
            case ir.Eval(expr=ir.PairOp() as p):
                return self.pair_op(p, st)
            case ir.If():
                return self.if_(s, st)
            case ir.Forever():
                return self.forever(s, st)
            case ir.Continue():
                if not self.loops:
                    raise SelectError("continue outside a loop")
                loop = self.loops[-1]
                loop.continues.append(st)
                return [W("jmp", "CONTINUE", ir.Sym(loop.top))], None
            case ir.Return():
                return self.return_(s, st)
        raise SelectError(f"no rule for statement {s}")

    def assign(self, t: ir.Var, value: ir.Expr, st: State):
        match t.storage:
            case ir.Acc():
                items, st = self.to_ac(value, st)
                return items, State(st.ac | {key(t)}, st.io)
            case ir.Io():
                if isinstance(value, ir.Var) and isinstance(value.storage, ir.Memory):
                    if key(value) in st.io:
                        return [], State(st.ac - {key(t)}, st.io | {key(t)})
                    return ([W("lio", "EX-LOAD-IO", mem(value))],
                            State(st.ac, frozenset({key(t), key(value)})))
                raise SelectError(f"{t.name}: only a memory operand can be loaded into IO")
        k = key(t)
        if value == ir.Const(0):
            return [W("dzm", "EX-STORE-ZERO", mem(t))], st.write_mem(k)
        items, st = self.to_ac(value, st)
        st = st.write_mem(k)
        return items + [W("dac", "EX-STORE", mem(t))], State(st.ac | {k}, st.io)

    def pair_op(self, p: ir.PairOp, st: State):
        if not isinstance(p.hi.storage, ir.Acc) or key(p.hi) not in st.ac:
            raise SelectError(f"{p.op}: {p.hi.name} must be an AC local holding its value")
        if not isinstance(p.lo.storage, ir.Io) or key(p.lo) not in st.io:
            raise SelectError(f"{p.op}: {p.lo.name} must be a register local holding its value")
        words = [W(PAIR_MNEMONIC[p.op], "EX-ROT", ir.ShiftCount(n)) for n in shift_chunks(p.count)]
        return words, State(frozenset({key(p.hi)}), frozenset({key(p.lo)}))

    def if_(self, s: ir.If, st: State):
        c = s.cond
        if isinstance(c.operand, ir.PreInc):
            t = c.operand.target
            pre: list[ir.Item] = []
            after = State(frozenset({key(t)}), st.io - {key(t)})
            skip_c = skips.isp_skip_when(c.op)
            skip_not_c = skips.isp_skip_when(skips.NEGATE[c.op])
        else:
            pre, after = self.to_ac(c.operand, st)
            skip_c = skips.ac_skip_when(c.op)
            skip_not_c = skips.ac_skip_when(skips.NEGATE[c.op])

        def skip_word(op: str, rule: str) -> ir.Word:
            if op == "isp":
                return W("isp", rule, mem(t), note=f"++{t.name} {c.op} 0")
            return W(op, rule, note=f"{c.op} 0")

        then_items, then_end = self.stmt(s.then, after)
        single = (s.orelse is None and skip_not_c is not None and len(then_items) == 1
                  and isinstance(then_items[0], ir.Word))
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
        start = self.counter
        assumed = st
        while True:
            self.counter = start
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

    def return_(self, s: ir.Return, st: State):
        items: list[ir.Item] = []
        if s.value is not None:
            items, st = self.to_ac(s.value, st)
        if s is self.last_return:
            return items + [ir.LabelDef(self.exit_label), W("jmp", "LAY-EXIT", ir.Here())], None
        return items + [W("jmp", "RET", ir.Sym(self.exit_label))], None

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
                raise SelectError(f"moving register local {e.name} into AC is not implemented yet")
            case ir.Var():
                if key(e) in st.ac:
                    return [], st
                return [W("lac", "EX-LOAD", mem(e))], State(frozenset({key(e)}), st.io)
            case ir.Const(value=v):
                return [self.const_ac(v)], State(frozenset(), st.io)
            case ir.PreInc(target=t):
                return [W("idx", "EX-INC", mem(t))], State(frozenset({key(t)}), st.io - {key(t)})
            case ir.Neg():
                items, st = self.to_ac(e.operand, st)
                return items + [W("cma", "EX-UNARY")], State(frozenset(), st.io)
            case ir.Binary():
                items, st = self.to_ac(e.left, st)
                return items + [W(BIN_MNEMONIC[e.op], "EX-BIN", self.memory_operand(e.right))], \
                    State(frozenset(), st.io)
            case ir.Shift():
                items, st = self.to_ac(e.operand, st)
                words = [W(SHIFT_MNEMONIC[e.op], "EX-SHIFT", ir.ShiftCount(n))
                         for n in shift_chunks(e.count)]
                return items + words, State(frozenset(), st.io)
        raise SelectError(f"no rule puts {e} in AC")

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
            case ir.Var(storage=s) if isinstance(s, ir.Memory):
                return mem(e)
        raise SelectError(f"right operand {e} must be a memory operand or a constant; "
                          "name a static to hold it")


def _ends_in_transfer(b: ir.Block) -> bool:
    return bool(b.stmts) and isinstance(b.stmts[-1], (ir.Return, ir.Forever))


def _last_return(node) -> ir.Return | None:
    match node:
        case ir.Return():
            return node
        case ir.Block():
            for s in reversed(node.stmts):
                r = _last_return(s)
                if r is not None:
                    return r
        case ir.If():
            return _last_return(node.orelse) or _last_return(node.then)
        case ir.Forever():
            return _last_return(node.body)
    return None
