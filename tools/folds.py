"""Folds: a bounded loop with no exit, laid out as the loop with exits it
stands for.

The vision's loop in a body is a fold: its count is fixed before it starts,
and no break, continue or return leaves it (CONTEXT.md 340-347). The
original's loops leave on a counter or on a value computed inside. RUNS
writes each as a fold whose steps after the exit do nothing: the count, or
a guard on a value that stays set once set, turns them off. `lower` turns
such a fold back into the loop with exits, statement for statement, so the
back end lays out the original's jumps. Each rule holds for every value the
fold can see, except that the loop runs past the fold's count where the
fold would stop: the count is a bound the source states, as `loop at most`
did, and the checks against the original test it.

The rules, each named in pdp1/README.md:

- A fold counted by a counter: `for _ in 1 .. -f:` whose body ends in
  `set f = f + 1` and sets f nowhere else, where f is below 0 and not -0
  when the fold starts. It is the index-and-skip loop on f: the body, then
  the step, left when f reaches 0.
- A loop rotated: the statements X just before `if f < 0:` around such a
  loop, whose body ends in X and the exit test, are the loop's first pass.
  The loop starts with X.
- A guarded fold: `for _ in 1 .. n:` whose body is guards on one test H. The passes
  after H fails do nothing, so H is tested only where it can change: each
  path through the body that ends with H known false ends in a break, one
  that ends with H known true goes round, and one that ends with H unknown
  tests it at the bottom. A guard inside the body whose value a path
  decides is dropped on that path; a path whose remaining statements are
  all guards it decides false jumps to the end of the pass. A local that
  only those guards read is then dead.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import runs

STATEMENTS = {"let", "set", "if", "loop", "for", "run", "emit", "match", "return", "break", "continue",
              "stop", "unreachable", "wait", "goto", "slots"}
NEGATED = {"<": ">=", ">=": "<", ">": "<=", "<=": ">", "==": "!=", "!=": "=="}


class FoldError(Exception):
    pass


def bare(x):
    """x without the source positions its statements carry."""
    if isinstance(x, list):
        return [bare(y) for y in x]
    if isinstance(x, tuple):
        if x and x[0] in STATEMENTS and isinstance(x[-1], str):
            x = x[:-1]
        return tuple(bare(y) for y in x)
    return x


def const(e):
    """The constant an expression is: an int, or a member; else None."""
    if e[0] == "num":
        return e[1]
    if e[0] == "neg" and e[1][0] == "num":
        return -e[1][1]
    if e[0] == "member":
        return e
    return None


def names_in(e) -> set[str]:
    """The fields (`record.field`) and locals an expression reads."""
    if not isinstance(e, tuple) or not e:
        return set()
    if e[0] == "field" and e[1][0] == "name":
        return {f"{e[1][1]}.{e[2]}"}
    if e[0] == "name":
        return {e[1]}
    if e[0] == "member":
        return set()
    out: set[str] = set()
    for x in e[1:]:
        if isinstance(x, tuple):
            out |= names_in(x)
        elif isinstance(x, list):
            for y in x:
                out |= names_in(y)
    return out


def target_names(t) -> set[str]:
    if t[0] == "tuple":
        return set().union(*(target_names(x) for x in t[1]))
    if t[0] == "index":
        return names_in(t[1])
    return names_in(t)


def writes(stmts: list, prog: runs.Program) -> set[str]:
    """What the statements may write: fields, locals, and `record.*` for a
    record a routine they run writes."""
    out: set[str] = set()
    for s in runs.walk_statements(stmts):
        if s[0] in ("let", "set"):
            out |= target_names(s[1])
        elif s[0] == "run" and s[1] in prog.routines:
            out |= {f"{r}.*" for r in prog.routines[s[1]].writes}
            out |= writes(prog.routines[s[1]].body, prog)
    return out


@dataclass(frozen=True)
class Known:
    """What a path knows of one place."""
    vals: frozenset | None = None       # the constants it may hold; None: any
    excl: frozenset = frozenset()       # constants it does not hold
    sign: str | None = None             # "neg" (sign bit set) or "nonneg"
    whole: bool = False                 # not -0

    def excluded(self, k) -> bool:
        return k in self.excl or self.vals is not None and k not in self.vals


def meet(a: Known, b: Known) -> Known:
    seen = a.excl | b.excl | (a.vals or frozenset()) | (b.vals or frozenset())
    return Known(vals=a.vals | b.vals if a.vals is not None and b.vals is not None else None,
                 excl=frozenset(k for k in seen if a.excluded(k) and b.excluded(k)),
                 sign=a.sign if a.sign == b.sign else None, whole=a.whole and b.whole)


class Facts:
    """What a path through a body knows: a Known for each place. None
    stands for a path that cannot run."""

    def __init__(self, prog: runs.Program, known: dict | None = None):
        self.prog = prog
        self.known = known or {}

    def get(self, e) -> Known | None:
        return self.known.get(bare(e))

    def put(self, e, k: Known) -> "Facts":
        return Facts(self.prog, {**self.known, bare(e): k})

    def kill(self, written: set[str]) -> "Facts":
        records = {w[:-2] for w in written if w.endswith(".*")}

        def hit(key) -> bool:
            return any(n in written or n.split(".")[0] in records for n in names_in(key))
        return Facts(self.prog, {k: v for k, v in self.known.items() if not hit(k)})

    # ---- deciding a condition

    def decide(self, c) -> bool | None:
        op = c[0]
        if op == "not":
            d = self.decide(c[1])
            return None if d is None else not d
        if op != "bin":
            return None
        o = c[1]
        if o in ("and", "or"):
            a, b = self.decide(c[2]), self.decide(c[3])
            if o == "and":
                return False if False in (a, b) else True if a and b else None
            return True if True in (a, b) else False if a is False and b is False else None
        if o in ("==", "!="):
            x, y = (c[3], c[2]) if const(c[2]) is not None and const(c[3]) is None else (c[2], c[3])
            k = const(y)
            if k is None:
                return None
            eq = self.equals(x, k)
            return None if eq is None else eq if o == "==" else not eq
        if o in ("<", ">=") and c[3] == ("num", 0):
            neg = self.negative(c[2])
            return None if neg is None else neg if o == "<" else not neg
        return None

    def equals(self, x, k) -> bool | None:
        if const(x) is not None:
            return const(x) == k
        kn = self.get(x)
        if kn is None:
            return None
        if kn.vals is not None and kn.vals == {k}:
            return True
        if kn.excluded(k):
            return False
        if isinstance(k, tuple):                        # a member: the others are excluded
            left = {m for m in self.prog.enums.get(k[1], []) if not kn.excluded(("member", k[1], m))}
            if left == {k[2]}:
                return True
        if isinstance(k, int) and kn.sign is not None and (k < 0) != (kn.sign == "neg"):
            return False
        return None

    def negative(self, x) -> bool | None:
        k = const(x)
        if isinstance(k, int):
            return k < 0
        kn = self.get(x)
        if kn is None:
            return None
        if kn.sign is not None:
            return kn.sign == "neg"
        if kn.vals and all(isinstance(v, int) for v in kn.vals):
            signs = {v < 0 for v in kn.vals}
            return signs.pop() if len(signs) == 1 else None
        return None

    # ---- learning from a test that passed or failed

    def learn(self, c, truth: bool) -> "Facts":
        op = c[0]
        if op == "not":
            return self.learn(c[1], not truth)
        if op != "bin":
            return self
        o = c[1]
        if o == "and" and truth or o == "or" and not truth:
            return self.learn(c[2], truth).learn(c[3], truth)
        if o in ("and", "or"):
            # and failed, or or passed: one side settles the other
            out = self
            if self.decide(c[2]) is (not truth):
                out = out.learn(c[3], truth)
            if self.decide(c[3]) is (not truth):
                out = out.learn(c[2], truth)
            return out
        if o in ("==", "!="):
            x, y = (c[3], c[2]) if const(c[2]) is not None and const(c[3]) is None else (c[2], c[3])
            k = const(y)
            if k is None or const(x) is not None:
                return self
            kn = self.get(x) or Known()
            if truth == (o == "=="):
                return self.put(x, holding(k))
            return self.put(x, replace(kn, excl=kn.excl | {k},
                                       vals=None if kn.vals is None else kn.vals - {k}))
        if o in ("<", ">=") and c[3] == ("num", 0) and const(c[2]) is None:
            kn = self.get(c[2]) or Known()
            return self.put(c[2], replace(kn, sign="neg" if truth == (o == "<") else "nonneg"))
        return self

    # ---- statements

    def after(self, s) -> "Facts":
        """The facts after a statement that is not an if."""
        op = s[0]
        if op in ("let", "set"):
            out = self.kill(target_names(s[1]))
            t, v = s[1], s[2]
            if t[0] == "tuple":
                return out
            if (k := const(v)) is not None:
                return out.put(t, holding(k))
            if v[0] == "bin" and v[1] == "+" and bare(v[2]) == bare(t) and v[3] == ("num", 1):
                return out.put(t, Known(whole=True))    # a step never gives -0
            return out
        if op == "run" and s[1] in self.prog.routines:
            r = self.prog.routines[s[1]]
            if r.kind == "processor" and len(s[2]) == len(r.params) and \
                    all(x[0] in ("let", "set", "emit") for x in r.body):
                from runsc import substitute
                out = self
                for x in substitute(list(r.body), dict(zip(r.params, s[2]))):
                    out = out.after(x)
                return out
            return self.kill(writes([s], self.prog))
        if op in ("loop", "for", "slots"):
            return self.kill(writes(s[-2], self.prog))
        return self


def holding(k) -> Known:
    """The Known of a place that holds the constant k."""
    if isinstance(k, int):
        return Known(vals=frozenset({k}), sign="neg" if k < 0 else "nonneg", whole=True)
    return Known(vals=frozenset({k}))


def merge(paths: list) -> Facts | None:
    live = [f for f in paths if f is not None]
    if not live:
        return None
    first, *rest = live
    known = dict(first.known)
    for f in rest:
        known = {k: meet(v, f.known[k]) for k, v in known.items() if k in f.known}
    return Facts(first.prog, known)


def negate(c):
    if c[0] == "bin" and c[1] in NEGATED:
        return ("bin", NEGATED[c[1]], c[2], c[3])
    if c[0] == "bin" and c[1] in ("and", "or"):
        return ("bin", "or" if c[1] == "and" else "and", negate(c[2]), negate(c[3]))
    if c[0] == "not":
        return c[1]
    return ("not", c)


def residue(c, facts: Facts):
    """c with each part the facts decide taken out (c not decided)."""
    if c[0] == "bin" and c[1] in ("and", "or"):
        a, b = facts.decide(c[2]), facts.decide(c[3])
        keep = True if c[1] == "and" else False
        if a is keep:
            return residue(c[3], facts)
        if b is keep:
            return residue(c[2], facts)
        return ("bin", c[1], residue(c[2], facts), residue(c[3], facts))
    return c


def guard_of(s):
    """The test of an if with one arm and no else, else None."""
    return s[1][0][0] if s[0] == "if" and len(s[1]) == 1 and not s[2] else None


def fold_test(s):
    """The test H of a guarded fold, `for _ in 1 .. n:` whose body is guards
    on H; else None. Its count is a bound: the loop it stands for keeps
    going where the fold stops with H still true."""
    if s[0] != "for" or s[2] != ("num", 1) or not s[4]:
        return None
    head = guard_of(s[4][0])
    if head is None or any(guard_of(x) is None or bare(guard_of(x)) != bare(head) for x in s[4]):
        return None
    return head


def step_of(s, prog: runs.Program):
    """The place s adds 1 to: `set f = f + 1`, or a run of a Processor
    whose body is only that."""
    if s[0] == "set" and s[2][0] == "bin" and s[2][1] == "+" and bare(s[2][2]) == bare(s[1]) \
            and s[2][3] == ("num", 1):
        return s[1]
    if s[0] == "run" and s[1] in prog.routines:
        r = prog.routines[s[1]]
        if r.kind == "processor" and len(r.body) == 1 and len(s[2]) == len(r.params):
            from runsc import substitute
            return step_of(substitute(r.body[0], dict(zip(r.params, s[2]))), prog)
    return None


# ---- the rules

class Lowering:
    def __init__(self, prog: runs.Program):
        self.prog = prog
        self.decided: set[str] = set()          # locals a decided guard read

    def block(self, stmts: list, facts: Facts | None) -> tuple[list, Facts | None]:
        out: list = []
        for s in stmts:
            if facts is None:
                out.append(s)
                continue
            op = s[0]
            if op == "if":
                arms, ends, prior = [], [], facts
                for c, b in s[1]:
                    nb, end = self.block(b, prior.learn(c, True))
                    arms.append((c, nb))
                    ends.append(end)
                    prior = prior.learn(c, False)
                other, end = self.block(s[2], prior)
                out.append(("if", arms, other, s[3]))
                facts = merge(ends + [end])
            elif op == "loop":
                inside = facts.kill(writes(s[2], self.prog))
                out.append(("loop", s[1], self.block(s[2], inside)[0], s[3]))
                facts = facts.after(s)
            elif op == "for":
                inside = facts.kill(writes(s[4], self.prog))
                s = (*s[:4], self.block(s[4], inside)[0], s[5])
                loop = self.counted(s, facts) or self.guarded(s, facts)
                out.extend(loop or [s])
                facts = facts.after(s)
            else:
                out.append(s)
                facts = facts.after(s)
        return rotated(out), facts

    def counted(self, s, facts: Facts) -> list | None:
        """A fold counted by a counter: the index-and-skip loop on it."""
        _, var, lo, hi, body, where = s
        if lo != ("num", 1) or hi[0] != "neg" or not body or runs.mentions(body, {var}):
            return None
        f = hi[1]
        if step_of(body[-1], self.prog) is None or bare(step_of(body[-1], self.prog)) != bare(f):
            return None
        if names_in(f) & writes(body[:-1], self.prog):
            raise FoldError(f"{where}: a fold counted by {f!r} sets it only in its last statement")
        kn = facts.get(f)
        if facts.negative(f) is not True or not (kn and kn.whole):
            raise FoldError(f"{where}: a fold counted by {f!r} starts where it is below 0 and not -0: "
                            f"inside `if f < 0:`, after a step of f or a set of f to a constant")
        leave = ("if", [(("bin", ">=", f, ("num", 0)), [("break", where)])], [], where)
        return [("loop", ("num", 0o400001), [*body, leave], where)]

    def guarded(self, s, facts: Facts) -> list | None:
        """A guarded fold: the loop whose exits are where its guard fails."""
        _, var, lo, hi, body, where = s
        if not body or guard_of(body[0]) is None:
            return None
        head = guard_of(body[0])
        firsts = {repr(bare(("bin", "==", ("name", var), lo)))}

        def other_reads(e) -> bool:
            if isinstance(e, tuple) and repr(bare(e)) in firsts:
                return False
            if e == ("name", var):
                return True
            return isinstance(e, (tuple, list)) and any(other_reads(x) for x in e)
        if other_reads(body):
            return None
        if any(guard_of(x) is None or bare(guard_of(x)) != bare(head) for x in body):
            if not writes(body, self.prog) & names_in(head):
                return None
            raise FoldError(f"{where}: a guarded fold's body is guards on one test, which the body sets")
        if lo != ("num", 1):
            raise FoldError(f"{where}: a guarded fold counts from 1: its count is the bound the loop it stands for "
                            f"keeps, and compiles to nothing")
        first = facts.learn(("bin", "==", ("name", var), lo), True) if const(lo) is not None else facts
        later = facts.learn(("bin", "==", ("name", var), lo), False) if const(lo) is not None else facts
        entry = first.decide(head)
        self.head, self.later = head, later
        start = facts.kill(writes(body, self.prog)).learn(head, True)
        inner, end = self.thread([*body[0][1][0][1], *body[1:]], start, [])
        if end is not None:
            inner += self.back(end, where, at_end=True)
        if entry is not True:
            inner = [("if", [(negate(residue(head, first)), [("break", where)])], [], where), *inner]
        if runs.mentions(inner, {var}):
            raise FoldError(f"{where}: a guarded fold reads its index {var} only in its guard, as {var} == {lo!r}")
        flags = {n for n in names_in(head) if "." not in n} & writes(body, self.prog)
        if left := runs.mentions([c for x in runs.walk_statements(inner) if x[0] == "if" for c, _ in x[1]], flags):
            raise FoldError(f"{where}: a guarded fold's test of {sorted(left)[0]} is not decided on every path")
        self.decided |= flags
        count = hi if lo == ("num", 1) else ("bin", "+", ("bin", "-", hi, lo), ("num", 1))
        if const(lo) is not None and const(hi) is not None:
            count = ("num", const(hi) - const(lo) + 1)
        return [("loop", count, flattened(inner), where)]

    def back(self, end: Facts, where: str, at_end: bool, skipped: bool = False) -> list:
        """What a path that reaches the end of the pass does: leave when
        the guard is known false there, go round when known true, test it
        at the bottom when unknown."""
        facts = self.at_head(end)
        d = facts.decide(self.head)
        if d is False:
            return [("break", where)]
        if d is True:
            return [("continue", where)] if skipped else []
        if not at_end:
            raise FoldError(f"{where}: a guarded fold's guard is unknown where a path jumps to the pass's end")
        return [("if", [(negate(residue(self.head, facts)), [("break", where)])], [], where)]

    def at_head(self, end: Facts) -> Facts:
        """The facts at the next pass's head: those of the path's end, and
        the index past its first value."""
        out = end
        for k, v in self.later.known.items():
            if k[0] == "name" and k not in end.known or k[0] == "name" and v.excl:
                out = out.put(k, v)
        return out

    def thread(self, stmts: list, facts: Facts, cont: list) -> tuple[list, Facts | None]:
        """stmts with each guard a path decides dropped or kept bare, and
        each path that ends the pass early ending in a jump. cont: the
        statements after stmts, out to the end of the body."""
        out: list = []
        stmts = list(stmts)
        k = 0
        while k < len(stmts):
            s, rest = stmts[k], stmts[k + 1:]
            g = guard_of(s)
            if g is not None and (d := facts.decide(g)) is not None:
                self.decided |= {n for n in names_in(g) if "." not in n}
                if d:
                    stmts = [*stmts[:k], *s[1][0][1], *rest]
                    facts = facts.learn(g, True)
                else:
                    k += 1
                continue
            if s[0] == "if":
                arms, ends, prior = [], [], facts
                for c, b in [*s[1], (None, s[2])]:
                    here = prior.learn(c, True) if c is not None else prior
                    if c is not None:
                        prior = prior.learn(c, False)
                    nb, end = self.thread(b, here, [rest, *cont])
                    after = [*rest, *[x for b2 in cont for x in b2]]
                    if end is not None and (c is not None or nb) and skips(after, end):
                        jump = self.back(end, s[-1], at_end=not after, skipped=bool(after))
                        jump = [] if jump and jump[0][0] == "if" else jump
                        if jump:
                            nb, end = [*nb, *jump], None
                    arms.append((c, nb))
                    ends.append(end)
                out.append(("if", arms[:-1], arms[-1][1], s[-1]))
                facts = merge(ends)
                if facts is None:
                    return out, None
            elif s[0] in ("break", "continue", "return", "stop", "unreachable"):
                out.append(s)
                return out, None
            else:
                out.append(s)
                facts = facts.after(s)
            k += 1
        return out, facts


def skips(stmts: list, facts: Facts) -> bool:
    """Every statement is a guard the facts decide false."""
    return all(guard_of(s) is not None and facts.decide(guard_of(s)) is False for s in stmts)


def flattened(stmts: list) -> list:
    """`if c: [..., break] else: E` is `if c: [..., break]`, then E."""
    out: list = []
    for s in stmts:
        if s[0] == "if":
            s = ("if", [(c, flattened(b)) for c, b in s[1]], flattened(s[2]), s[3])
            if len(s[1]) == 1 and s[2] and s[1][0][1] and s[1][0][1][-1][0] in ("break", "continue"):
                out.append(("if", s[1], [], s[3]))
                out.extend(s[2])
                continue
        elif s[0] == "loop":
            s = ("loop", s[1], s[2], s[3])
        out.append(s)
    return out


def rotated(stmts: list) -> list:
    """The statements X just before `if c:` around a loop whose body ends
    in X and a test of c's negation that breaks: the loop's first pass."""
    out: list = []
    for s in stmts:
        g = guard_of(s)
        loop = s[1][0][1][0] if g is not None and len(s[1][0][1]) == 1 and s[1][0][1][0][0] == "loop" else None
        end = loop[2][-1] if loop and loop[2] else None
        if end is not None and guard_of(end) is not None and bare(end[1][0][1]) == [("break",)] \
                and bare(guard_of(end)) == bare(negate(g)):
            body = loop[2][:-1]
            for n in range(min(len(body), len(out)), 0, -1):
                if bare(body[-n:]) == bare(out[-n:]):
                    from runsc import trailing_continues
                    x = body[-n:]
                    del out[-n:]
                    out.append(("loop", loop[1], [*x, end, *trailing_continues(body[:-n])], loop[3]))
                    break
            else:
                out.append(s)
            continue
        out.append(s)
    return out


def settled(stmts: list, prog: runs.Program) -> list:
    """Each guard with one arm and no else that the sets just before it
    decide: its arm when true, nothing when false. A loop bundle's counter
    set to a constant below 0 needs no test before the first pass (the
    `setup` and `count` macros: head_out's three passes)."""
    out: list = []
    facts = Facts(prog)
    for s in stmts:
        g = guard_of(s)
        if g is not None and (d := facts.decide(g)) is not None:
            out.extend(s[1][0][1] if d else [])
            facts = Facts(prog)
            continue
        out.append(s)
        facts = facts.after(s) if s[0] in ("let", "set") else Facts(prog)
    return out


def dead_locals(stmts: list, names: set[str]) -> list:
    """stmts without the lets and sets of each of names no statement reads."""
    read = set()
    for s in runs.walk_statements(stmts):
        parts = {"if": lambda: [c for c, _ in s[1]], "loop": lambda: [s[1]], "for": lambda: [s[2], s[3]],
                 "slots": lambda: [s[2], s[3]], "match": lambda: [s[1]]}.get(
            s[0], lambda: [x for x in s[1:] if isinstance(x, (tuple, list))])()
        if s[0] in ("let", "set"):
            parts = [s[2]] + ([s[1][2]] if s[1][0] == "index" else [])
        read |= runs.mentions(parts, names)
    dead = names - read

    def go(xs):
        out = []
        for s in xs:
            if s[0] in ("let", "set") and s[1][0] == "name" and s[1][1] in dead:
                continue
            if s[0] == "if":
                s = ("if", [(c, go(b)) for c, b in s[1]], go(s[2]), s[3])
            elif s[0] in ("loop", "for", "slots"):
                s = (*s[:-2], go(s[-2]), s[-1])
            out.append(s)
        return out
    return go(stmts)


def lower(stmts: list, prog: runs.Program) -> list:
    """A routine's body with each fold that stands for a loop with exits
    laid out as that loop."""
    low = Lowering(prog)
    out, _ = low.block(stmts, Facts(prog))
    return dead_locals(out, low.decided)
