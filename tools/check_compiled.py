"""The image must come from the RUNS text, not from the binding. Builds the
image once (it must match the oracle), then mutates the RUNS of every
routine and field the bindings compile, one change at a time:

- each number one up; each field's initial value: a number one up, a
  member to each other member, an instruction to cma;
- each field reference to each other field of its Record (of its type, and
  of another type), and to the field of the same name in another Record;
- each operator to another (+ and -, < and >=, & and |, and and or, ...);
- each enum member to another of its enum;
- each run of a routine to each other routine of its kind and arity, and
  each of its arguments to 0, to 1, to itself plus 1, to its negation and
  to each other name in scope;
- each guard negated; an if's arm swapped with its else, and its first two
  arms with each other; each two arms of a match swapped;
- each statement deleted, duplicated, swapped with the next, and moved to
  every other place in its block;
- a statement inserted after each let and set: a set of each other place
  the routine sets to the same value; and a step of its own place
  (`set p = p + 1`) inserted before it and after it;
- each set of a field at a Processor's top level made a local of the
  field's name, which the Processor's later statements read instead;
- each Record a Processor declares under reads: or writes:, and each
  requires:, deleted;

and mutates each binding: each key line and each section deleted, each
element of a list or an inline table deleted, and each value replaced (a
name by each other name of its shape the binding uses, a number one up and
one down, a flag flipped). A binding mutant must build another image or be
refused; one that builds the image is dead, unless the value it replaced is
a name the binding gives a C word (a cursor, the table, a block, an exit,
a slot), which never reaches the image: it is renamed.

Each RUNS mutant is classified. It changes the image; or the evaluator
rejects the text before anything runs (runs.check); or runsc refuses it
with a BindError naming the RUNS construct. A mutant that builds the
original image is silent, and passes only when the evaluator shows it is
the same game: the mutated routine, and failing that each bound routine
that compiles it, fired on seeded random Records before and after the
mutation must leave the same Records, the same points and the same error,
with at least a quarter of the firings running clean. A silent initial
value passes when 60 games of 30 frames from power-on, played before and
after, put out the same at every firing and end with the same Records but
for the field itself. A requires: is a
precondition, not code: its deletion passes when every firing it lets run
leaves the same, and it stops some firing (else it is dead). Any other
silent mutant, and any crash of runsc, fails the gate. A loop's bound is
RUNS's check that the loop ends, not code, and compiles to nothing: a
mutant of it is not built, and passes when every firing leaves the same or
stops the mutant at its bound. A guarded fold's count is such a bound
(folds.py): the loop it stands for keeps going where the fold stops, so a
firing whose fold ends its count with its guard still true ran past it.

Usage: [--sample N] [--only TEXT] [--kinds a,b] (build N mutants drawn by
a seeded shuffle, not all; only those whose label holds TEXT; only those
kinds).
Run from the repository root:
  uv run python tools/check_compiled.py"""
from __future__ import annotations

import dataclasses
import multiprocessing
import random
import re
import shutil
import sys
import tempfile
import tomllib
import zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import folds
import runs
import runsc
from runsc import dotted_of

OPERATORS = {"+": "-", "-": "+", "&": "|", "|": "&", "^": "|", "<<": ">>", ">>": "<<",
             "<": ">=", ">=": "<", ">": "<=", "<=": ">", "==": "!=", "!=": "==", "and": "or", "or": "and"}
STATEMENTS = {"let", "set", "if", "loop", "for", "break", "continue", "stop", "unreachable", "wait",
              "return", "jump", "emit", "run", "match"}
TRIALS = 200                # seeded Record states a silent mutant is fired on
CLEAN = TRIALS // 4         # firings that must run without error and reach the mutated routine
PLAYS = 60                  # Records as play leaves them, kept before a routine's firings
EDGES = [0, runs.MASK, 1, runs.MASK ^ 1, 0o377777, 0o400000, 0o777, 0o400777]   # 0, -0, 1, -1, the extremes
AT_BOUND = re.compile(r"ran past (its bound of )?\d+|the bound is no count")   # a firing a bound stops
BOUNDED = ("number", "field", "field type", "field record", "operator", "member")   # kinds a loop's bound holds


@dataclasses.dataclass(frozen=True)
class Mutant:
    label: str
    kind: str
    routine: str | None     # the routine mutated; None for a field's initial value
    path: tuple             # into the routine's body; (record, field, path) of an initial value; (clause, value)
    new: object = None      # the node put at path; the statement inserted; the place a statement moves to


def replaced(tree, path, new):
    if not path:
        return new
    k = path[0]
    if isinstance(tree, dict):
        return {**tree, k: replaced(tree[k], path[1:], new)}
    items = list(tree)
    items[k] = replaced(tree[k], path[1:], new)
    return items if isinstance(tree, list) else tuple(items)


def replaced_all(tree, old, new):
    """tree with every node equal to old as new."""
    if tree == old:
        return new
    if isinstance(tree, list):
        return [replaced_all(t, old, new) for t in tree]
    if isinstance(tree, tuple):
        return tuple(replaced_all(t, old, new) for t in tree)
    if isinstance(tree, dict):
        return {k: replaced_all(v, old, new) for k, v in tree.items()}
    return tree


def unplaced(tree):
    """tree without the source lines its statements carry."""
    if isinstance(tree, tuple) and tree and tree[0] in STATEMENTS and isinstance(tree[-1], str):
        return tuple(unplaced(x) for x in tree[:-1])
    if isinstance(tree, (list, tuple)):
        return type(tree)(unplaced(x) for x in tree)
    if isinstance(tree, dict):
        return {k: unplaced(v) for k, v in tree.items()}
    return tree


def at(tree, path):
    for k in path:
        tree = tree[k]
    return tree


def nodes(tree, path=()):
    """(path, node) of every list, tuple and match arm of a tree."""
    yield path, tree
    if isinstance(tree, (list, tuple)):
        for k, t in enumerate(tree):
            yield from nodes(t, path + (k,))
    elif isinstance(tree, dict):
        for k, t in tree.items():
            yield from nodes(t, path + (k,))


def is_statement(s) -> bool:
    return isinstance(s, tuple) and bool(s) and s[0] in STATEMENTS and isinstance(s[-1], str)


def is_block(x) -> bool:
    return isinstance(x, list) and bool(x) and all(is_statement(s) for s in x)


def line(s) -> str:
    return s[-1].rsplit("/", 1)[-1]


def compiled(prog: runs.Program, name: str, bound: set[str]):
    """The routines a bound routine compiles: itself, and the ones its
    Network runs that are not bound routines of their own."""
    yield name
    for inner in sorted(runs.runs_of(prog.routines[name].body) - bound):
        yield from compiled(prog, inner, bound)


def bound_places(prog: runs.Program):
    specs = [tomllib.loads(b.read_text()) for b in sorted(runsc.BINDINGS.glob("*.toml")) if b.name != runsc.DEVICES]
    places = [p for spec in specs for p in spec.get("place", []) + spec.get("inline", []) + spec.get("code", [])]
    # a declaration naming a routine with Ports declares each of its copies (runsc copies_of)
    places = [{**p, "routine": c} if p.get("routine") in prog.templates else p for p in places
              for c in ([c for c, (t, _) in prog.copies.items() if t == p["routine"]]
                        if p.get("routine") in prog.templates else [None])]
    return specs, places, {p["routine"] for p in places if "routine" in p}


def owners(prog: runs.Program) -> dict[str, list[str]]:
    """Each compiled routine -> the bound routines whose code holds it."""
    _, _, bound = bound_places(prog)
    out: dict[str, list[str]] = {}
    for name in sorted(bound):
        for proc in dict.fromkeys(compiled(prog, name, bound)):
            out.setdefault(proc, []).append(name)
    return out


def targets(body) -> list:
    """Every place a routine's lets and sets write: locals, fields, slots."""
    return sorted({s[1] for _, s in nodes(body) if is_statement(s) and s[0] in ("let", "set")
                   and s[1][0] != "tuple"}, key=repr)


def expression_sites(prog: runs.Program, proc: str, path, node):
    if node[0] == "num":
        yield Mutant(f"{proc} {path} {node[1]:o}", "number", proc, path, ("num", node[1] + 1))
    elif node[0] == "field" and node[1][0] == "name" and node[1][1] in prog.records:
        rec = prog.records[node[1][1]]
        typ = rec.fields[node[2]][0]
        for f, (t, _) in rec.fields.items():
            if f != node[2]:
                yield Mutant(f"{proc} field {rec.name}.{node[2]} -> {f} {path}", "field" if t == typ else "field type",
                             proc, path, ("field", node[1], f))
        for other in sorted(prog.records):
            if other != rec.name and node[2] in prog.records[other].fields:
                yield Mutant(f"{proc} field {rec.name}.{node[2]} -> {other}.{node[2]} {path}", "field record",
                             proc, path, ("field", ("name", other), node[2]))
    elif node[0] == "bin" and node[1] in OPERATORS:
        yield Mutant(f"{proc} operator {node[1]} -> {OPERATORS[node[1]]} {path}", "operator", proc, path,
                     ("bin", OPERATORS[node[1]], *node[2:]))
    elif len(node) == 2 and node[0] == "name" and isinstance(node[1], str) \
            and node[1] not in prog.routines[proc].params:
        for members in prog.enums.values():
            if node[1] in members:
                other = next(m for m in members if m != node[1])
                yield Mutant(f"{proc} member {node[1]} -> {other} {path}", "member", proc, path, ("name", other))


def statement_sites(prog: runs.Program, proc: str, path, s):
    if s[0] == "run":
        callee = prog.routines[s[1]]
        for name, r in sorted(prog.routines.items()):
            if name != s[1] and r.kind == callee.kind and len(r.params) == len(callee.params):
                yield Mutant(f"{proc} run {s[1]} -> {name} @{line(s)}", "run", proc, path, ("run", name, *s[2:]))
        scope = prog.routines[proc].params + [x[1] for _, x in nodes(prog.routines[proc].body)
                                              if is_statement(x) and x[0] == "for"]
        for k, a in enumerate(s[2]):
            others = [("num", 0), ("num", 1), ("bin", "+", a, ("num", 1)), ("neg", a)]
            candidates = others + [("name", n) for n in scope]
            for j, new in enumerate(candidates):
                if new != a and new not in candidates[:j]:
                    yield Mutant(f"{proc} run {s[1]} argument {k} -> {new} @{line(s)}", "argument", proc, path,
                                 ("run", s[1], replaced(s[2], (k,), new), *s[3:]))
    elif s[0] == "if":
        arms, other = s[1], s[2]
        for k, (c, body) in enumerate(arms):
            yield Mutant(f"{proc} negate guard {k} @{line(s)}", "negate", proc, path,
                         ("if", replaced(arms, (k, 0), ("not", c)), other, s[3]))
        if other:
            yield Mutant(f"{proc} if/else swapped @{line(s)}", "branches", proc, path,
                         ("if", [(arms[0][0], other)] + arms[1:], arms[0][1], s[3]))
        if len(arms) > 1:
            yield Mutant(f"{proc} arms 0/1 swapped @{line(s)}", "branches", proc, path,
                         ("if", [(arms[0][0], arms[1][1]), (arms[1][0], arms[0][1])] + arms[2:], other, s[3]))
    elif s[0] == "match":
        keys = list(s[2])
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                yield Mutant(f"{proc} match arms {a}/{b} swapped @{line(s)}", "arms", proc, path,
                             ("match", s[1], {**s[2], a: s[2][b], b: s[2][a]}, s[3]))


def block_sites(prog: runs.Program, proc: str, path, block, places):
    for k, s in enumerate(block):
        here = path + (k,)
        if len(block) > 1:
            yield Mutant(f"{proc} delete {s[0]} @{line(s)}", "delete", proc, here)
        if k + 1 < len(block):
            yield Mutant(f"{proc} swap {s[0]}/{block[k + 1][0]} @{line(s)}", "swap", proc, here)
        yield Mutant(f"{proc} duplicate {s[0]} @{line(s)}", "duplicate", proc, here)
        for j in range(len(block)):
            if abs(j - k) > 1:
                yield Mutant(f"{proc} move {s[0]} @{line(s)} to {j}", "move", proc, here, j)
        if s[0] in ("let", "set") and s[1][0] != "tuple":
            for t in places:
                if t != s[1]:
                    yield Mutant(f"{proc} insert after @{line(s)}: set {dotted_of(t) or t} to its value", "insert",
                                 proc, path + (k + 1,), ("set", t, s[2], s[3]))
            step = ("set", s[1], ("bin", "+", s[1], ("num", 1)), s[3])
            yield Mutant(f"{proc} insert a step before @{line(s)}", "insert", proc, here, step)
            yield Mutant(f"{proc} insert a step after @{line(s)}", "insert", proc, path + (k + 1,), step)


def routine_sites(prog: runs.Program, proc: str):
    r = prog.routines[proc]
    places = targets(r.body)
    for path, node in nodes(r.body):
        if is_statement(node):
            yield from statement_sites(prog, proc, path, node)
        elif isinstance(node, tuple) and node and isinstance(node[0], str):
            yield from expression_sites(prog, proc, path, node)
        if path == () and r.kind == "processor":
            own = runsc.routine_locals(r)
            for k, s in enumerate(node):
                fields = [x for x in (s[1][1] if s[1][0] == "tuple" else [s[1]]) if x[0] == "field"]
                if s[0] == "set" and fields and not {x[2] for x in fields} & own:
                    yield Mutant(f"{proc} local {', '.join(dotted_of(x) for x in fields)} @{line(s)}", "local",
                                 proc, (k,))
        if is_block(node):
            yield from block_sites(prog, proc, path, node, places)
    for clause in ("reads", "writes"):
        for rec in sorted(getattr(r, clause)):
            yield Mutant(f"{proc} drop {clause}: {rec}", "declaration", proc, (clause, rec))
    for k, _ in enumerate(r.requires):
        yield Mutant(f"{proc} drop requires {k}", "requires", proc, ("requires", k))


def sites(prog: runs.Program) -> list[Mutant]:
    """Every mutant of the routines the bindings compile, and of every
    field's initial value."""
    out: list[Mutant] = []
    for proc in owners(prog):
        out += routine_sites(prog, proc)
    for rec, r in prog.records.items():
        for fld, (typ, init) in r.fields.items():
            for path, node in nodes(init or ()):
                for new in initial_mutants(prog, typ, node):
                    out.append(Mutant(f"{rec}.{fld} = {node} -> {new} {path}", "initial", None, (rec, fld, path),
                                      new))
    return out


def initial_mutants(prog: runs.Program, typ: str, node) -> list:
    """A number one up; a member to each other member of its field's enum; an
    instruction to cma."""
    if not isinstance(node, tuple) or not node:
        return []
    if node[0] == "num":
        return [("num", node[1] + 1)]
    if node[0] == "name" and typ in prog.enums:
        return [("name", m) for m in prog.enums[typ] if m != node[1]]
    if typ == runs.INSN and (node[0] == "call" or node[0] == "name") and node != ("name", "cma"):
        return [("name", "cma")]
    return []


def is_bound(prog: runs.Program, m: Mutant) -> bool:
    """A mutant anywhere in a loop's bound expression."""
    if m.kind not in BOUNDED:
        return False
    node = prog.routines[m.routine].body
    for k in m.path:
        if isinstance(node, tuple) and (node[:1] == ("loop",) and k == 1 or node[:1] == ("jump",) and k == 2
                                        or k == 3 and is_statement(node) and folds.fold_test(node) is not None):
            return True
        node = node[k]
    return False


def mutate(prog: runs.Program, m: Mutant) -> runs.Program:
    if m.kind == "initial":
        rec, fld, path = m.path
        r = prog.records[rec]
        typ, init = r.fields[fld]
        fields = {**r.fields, fld: (typ, replaced(init, path, m.new))}
        return dataclasses.replace(prog, records={**prog.records, rec: runs.Record(rec, r.count, fields, r.stream)})
    r = prog.routines[m.routine]
    body, reads, writes, requires = r.body, r.reads, r.writes, r.requires
    if m.kind == "local":
        (k,) = m.path
        s = r.body[k]
        target, rest = s[1], r.body[k + 1:]
        for x in (s[1][1] if s[1][0] == "tuple" else [s[1]]):
            if x[0] == "field":
                target, rest = replaced_all(target, x, ("name", x[2])), replaced_all(rest, x, ("name", x[2]))
        body = r.body[:k] + [("let", target, s[2], s[3])] + rest
    elif m.kind in ("delete", "swap", "duplicate", "move", "insert"):
        *where, k = m.path
        block = list(at(r.body, where))
        if m.kind == "delete":
            del block[k]
        elif m.kind == "swap":
            block[k], block[k + 1] = block[k + 1], block[k]
        elif m.kind == "duplicate":
            block.insert(k, block[k])
        elif m.kind == "move":
            block.insert(m.new, block.pop(k))
        else:
            block.insert(k, m.new)
        body = replaced(r.body, tuple(where), block)
    elif m.kind == "declaration":
        clause, rec = m.path
        reads, writes = (reads - {rec}, writes) if clause == "reads" else (reads, writes - {rec})
    elif m.kind == "requires":
        requires = [c for k, c in enumerate(requires) if k != m.path[1]]
    else:
        body = replaced(r.body, m.path, m.new)
    new = runs.Routine(r.kind, r.name, r.params, body, reads, writes, requires)
    return dataclasses.replace(prog, routines={**prog.routines, r.name: new})


# ---------------------------------------------------------------- evaluator

def call_arguments(prog: runs.Program) -> dict[str, list[list]]:
    """Each routine's argument lists, as its runs write them."""
    out: dict[str, list[list]] = {}
    for r in prog.routines.values():
        for _, node in nodes(r.body):
            if is_statement(node) and node[0] == "run":
                out.setdefault(node[1], []).append(node[2])
    return out


def random_state(prog: runs.Program, rng: random.Random) -> dict:
    """Every word of every Record drawn at random, a quarter of them from the
    words at the edges, every enum field a member drawn at random;
    instructions and streams as the program starts them."""
    m = runs.Machine(prog)

    def word() -> runs.W:
        return runs.W(rng.choice(EDGES) if rng.random() < 0.25 else rng.randrange(1 << 18))
    for name, rec in prog.records.items():
        if rec.stream:
            continue
        for fld, (typ, _) in rec.fields.items():
            draw = word if typ == "word" else \
                (lambda t=typ: runs.Member(t, rng.choice(prog.enums[t]))) if typ in prog.enums else None
            if draw is None:
                continue
            if rec.count is None:
                m.state[name][fld] = draw()
            else:
                m.state[name][fld] = [draw() for _ in range(rec.count)]
    return m.state


def arguments(prog: runs.Program, name: str, calls: dict, rng: random.Random) -> list:
    params = prog.routines[name].params
    if not params:
        return []
    written = rng.choice(calls[name]) if calls.get(name) else [("name", p) for p in params]
    return [runs.word_of(a[1]) if a[0] == "num" else rng.choice([0, 1, rng.randrange(0o30)]) for a in written]


def copied(state: dict) -> dict:
    """Records hold words, members and instructions, which never change:
    a copy copies only the dicts and lists that hold them."""
    return {r: {f: list(v) if isinstance(v, list) else v for f, v in d.items()} if isinstance(d, dict) else list(d)
            for r, d in state.items()}


class Bounded(runs.Machine):
    """The evaluator, stopping a guarded fold that ends its count with its
    guard still true: it ran past its bound, as `loop at most` does."""
    tests: dict[int, tuple] = {}            # id of a for -> (the for, its fold's test or None)

    def stmt(self, s, scope):
        out = super().stmt(s, scope)
        if s[0] == "for":
            kept = self.tests.get(id(s))
            if kept is None or kept[0] is not s:
                kept = self.tests[id(s)] = (s, folds.fold_test(s))
            if kept[1] is not None:
                n = runs.as_count(self.eval(s[3], scope))
                scope.locals[s[1]] = n + 1          # the next pass, which the loop would run
                if self.truth(self.eval(kept[1], scope)):
                    raise runs.RunsError(f"{s[-1]}: fold ran past its bound of {n}")
        return out


def fire(prog: runs.Program, name: str, args: list, state: dict):
    """What one firing leaves: the Records and the routine code jumped to,
    or the error it stopped with; and the routines it ran."""
    m = Bounded(prog)
    m.state = copied(state)
    try:
        m.run(name, args)
    except runs.Stop:
        return ("stop", m.state), {n for n, _ in m.fired}
    except (runs.RunsError, runs.Return, runs.Break, runs.Continue) as e:
        return (f"error {type(e).__name__}: {e}", None), {n for n, _ in m.fired}
    return (m.jumped_to, m.state), {n for n, _ in m.fired}


PLAYED: dict[str, list] = {}


def played(prog: runs.Program) -> dict[str, list]:
    """Records as play leaves them: each routine -> (arguments, Records)
    just before some of its firings, from games the evaluator plays from
    the tape's words with random power-on words and console settings, the
    control boxes drawn anew each frame. Random Records seldom take a long routine
    (the outline compiler, the spaceship) clean to its end; these do."""
    if PLAYED:
        return PLAYED
    kept: dict[str, list] = {}

    class Recorder(runs.Machine):
        def run(self, name, args=()):
            if len(kept.setdefault(name, [])) < PLAYS:
                kept[name].append((list(args), copied(self.state)))
            return super().run(name, args)
    for _ in games(prog, Recorder, random.Random(1962)):
        pass
    PLAYED.update(kept)
    return PLAYED


def games(prog: runs.Program, machine, rng: random.Random):
    """60 games of 30 frames from power-on: the tape's words, random
    power-on words and console settings, the control boxes drawn anew each
    frame. Yields what leaves the game at each firing (the streams and the
    lights), and the Records at the game's end, or the error it stops with."""
    streams = [r.name for r in prog.records.values() if r.stream]
    for game in range(60):
        m = machine(prog)
        world = random_state(prog, rng)
        for rec in ("console", "score"):            # what comes in: the switches, the power-on words
            m.state[rec] = world[rec]
        try:
            m.run(["start_with_control_boxes", "start_with_test_word"][game % 2])
            for _ in range(30):
                yield {r: m.state[r] for r in streams + ["lights"]}
                m.state["console"]["control_boxes"] = runs.W(rng.randrange(1 << 18))
                for stream in streams:
                    m.state[stream] = []
                m.run("tick")
            yield copied(m.state)
        except (runs.RunsError, runs.Stop) as e:
            yield f"{type(e).__name__}: {e}"


def from_power_on(prog: runs.Program, mutated: runs.Program, rec: str, fld: str) -> tuple[bool, str]:
    """An initial value changed: the games from power-on, played before and
    after on the same inputs, put out the same at every firing and leave the
    same Records at their end, but for the changed field itself, which no
    firing then has read to any effect."""
    def end(x):
        if isinstance(x, dict) and rec in x and isinstance(x[rec], dict):
            return {**x, rec: {**x[rec], fld: None}}
        return x
    k = 0
    for k, (a, b) in enumerate(zip(games(prog, runs.Machine, random.Random(1962)),
                                    games(mutated, runs.Machine, random.Random(1962)))):
        if end(a) != end(b):
            return False, f"firing {k} from power-on differs"
    return True, f"{k + 1} firings from power-on, all the same"


def same_game(prog: runs.Program, mutated: runs.Program, name: str, seed: str,
              mutated_routine: str | None = None) -> tuple[bool, str]:
    """Fire name before and after the mutation on the same seeded Records,
    and on Records as play leaves them before its firings: the same
    Records, points and error every time, with enough firings that run
    clean through the mutated routine."""
    rng = random.Random(zlib.crc32(seed.encode()))
    calls = call_arguments(prog)
    clean = 0
    trials = [(arguments(prog, name, calls, rng), random_state(prog, rng)) for _ in range(TRIALS)] \
        + played(prog).get(name, [])
    for k, (args, state) in enumerate(trials):
        (a, ran), (b, _) = fire(prog, name, args, state), fire(mutated, name, args, state)
        if a != b:
            return False, f"{name}{tuple(args)} trial {k}: {str(a[0])[:80]} / {str(b[0])[:80]}"
        clean += not str(a[0]).startswith("error") and (mutated_routine or name) in ran
    if clean < CLEAN:
        return False, f"{name}: only {clean} of {len(trials)} firings ran clean through {mutated_routine or name}"
    return True, f"{name}: {len(trials)} firings, {clean} clean through {mutated_routine or name}"


def equivalent(prog: runs.Program, mutated: runs.Program, m: Mutant) -> tuple[bool, str]:
    """The mutated routine, then each bound routine that compiles it, fired
    before and after on the same seeded Records."""
    if m.kind == "initial":
        return from_power_on(prog, mutated, *m.path[:2])
    if unplaced(mutated.routines[m.routine].body) == unplaced(prog.routines[m.routine].body) \
            and m.kind not in ("declaration", "requires"):
        return True, "the same text (identical statements swapped)"
    why = []
    for name in [m.routine] + [o for o in owners(prog).get(m.routine, []) if o != m.routine]:
        ok, how = same_game(prog, mutated, name, m.label, m.routine)
        if ok:
            return True, how
        why.append(how)
    return False, "; ".join(why)


def precondition(prog: runs.Program, mutated: runs.Program, m: Mutant) -> tuple[bool, str]:
    """A requires: deleted. It is the port's check that a firing is one the
    game makes, not code: every firing it lets run must leave the same
    Records, and it must stop some firing, or it says nothing."""
    rng = random.Random(zlib.crc32(m.label.encode()))
    calls = call_arguments(prog)
    stopped = clean = 0
    for k in range(4 * TRIALS):
        if k >= TRIALS and stopped and clean >= CLEAN:
            break
        state = random_state(prog, rng)
        args = arguments(prog, m.routine, calls, rng)
        (a, _), (b, _) = fire(prog, m.routine, args, state), fire(mutated, m.routine, args, state)
        if str(a[0]).endswith("precondition fails"):
            stopped += 1
        elif a != b:
            return False, f"{m.routine}{tuple(args)} trial {k}: {str(a[0])[:80]} / {str(b[0])[:80]}"
        else:
            clean += not str(a[0]).startswith("error")
    if not stopped or clean < CLEAN:
        return False, f"{m.routine}: the precondition stopped {stopped} of {k + 1} firings, {clean} ran clean"
    return True, f"{m.routine}: stopped {stopped} of {k} firings, the other {k - stopped} the same, {clean} clean"


def bounded(prog: runs.Program, mutated: runs.Program, m: Mutant) -> tuple[bool, str]:
    """A loop's bound changed. It is the port's check that the loop ends,
    not code: every firing must leave the same, or stop one of the two at
    the bound it states."""
    rng = random.Random(zlib.crc32(m.label.encode()))
    calls = call_arguments(prog)
    stopped = 0
    for k in range(TRIALS):
        state = random_state(prog, rng)
        args = arguments(prog, m.routine, calls, rng)
        (a, _), (b, _) = fire(prog, m.routine, args, state), fire(mutated, m.routine, args, state)
        if a != b and not any(AT_BOUND.search(str(x[0])) for x in (a, b)):
            return False, f"{m.routine}{tuple(args)} trial {k}: {str(a[0])[:80]} / {str(b[0])[:80]}"
        stopped += a != b
    return True, f"{m.routine}: {TRIALS} firings, {stopped} stopped at a bound, the rest the same"


# ---------------------------------------------------------------- the binding

@dataclasses.dataclass(frozen=True)
class Edit:
    """A binding mutant: the text of one binding file from start to end
    replaced by new."""
    label: str
    kind: str               # key (a key line or a section deleted), element, value
    file: str
    start: int
    end: int
    new: str = ""
    renames: bool = False   # the value is a name the binding gives a C word


def key_edits(name: str, text: str) -> list[Edit]:
    """Each whole key = value line, and each [section] or [[place]] with its keys, deleted."""
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for t in lines:
        offsets.append(offsets[-1] + len(t))
    heads = [n for n, t in enumerate(lines) if t.startswith("[")] + [len(lines)]
    out = [Edit(f"{name}:{a + 1} section", "key", name, offsets[a], offsets[z]) for a, z in zip(heads, heads[1:])]
    for n, t in enumerate(lines):
        s = t.strip()
        if s and not s.startswith(("#", "[")) and "=" in s and s.count("[") == s.count("]") \
                and s.count("{") == s.count("}"):
            out.append(Edit(f"{name}:{n + 1} key", "key", name, offsets[n], offsets[n + 1]))
    return out


def values(text: str):
    """(kind, start, end) of each value of a TOML text: each quoted name
    (keys and section names too), each number and flag; and (kind, start,
    end, items) of each list and inline table, items the (start, end) of a
    list's elements. Comments are not values."""
    k, stack, after_eq = 0, [], False
    while k < len(text):
        c = text[k]
        number = re.match(r"(0o[0-7]+|\d+|true|false)\b", text[k:]) if (after_eq or stack) \
            and not (text[k - 1].isalnum() or text[k - 1] in "_.") else None
        if c == "#":
            nl = text.find("\n", k)
            k = len(text) if nl < 0 else nl
            continue
        if c == "\n" and not stack:
            after_eq = False
        elif c == "=":
            after_eq = True
        elif c == '"':
            end = text.index('"', k + 1) + 1
            yield "string", k, end
            if stack and stack[-1][0] == "[":
                stack[-1][2].append((k, end))
            k = end
            continue
        elif c in "[{" and (after_eq or stack):
            stack.append((c, k, []))
        elif c in "]}" and stack:
            kind, start, items = stack.pop()
            yield ("list" if kind == "[" else "table"), start, k + 1, items
            if stack and stack[-1][0] == "[":
                stack[-1][2].append((start, k + 1))
        elif number:
            yield ("flag" if number.group(1) in ("true", "false") else "number"), k, k + number.end()
            if stack and stack[-1][0] == "[":
                stack[-1][2].append((k, k + number.end()))
            k += number.end()
            continue
        k += 1


def table_entries(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """The (start, end) of each key = value entry of an inline table."""
    inner, out, depth, begin = text[start + 1:end - 1], [], 0, 0
    quoted = False
    for i, c in enumerate(inner + ","):
        if c == '"':
            quoted = not quoted
        elif not quoted and c in "[{":
            depth += 1
        elif not quoted and c in "]}":
            depth -= 1
        elif not quoted and depth == 0 and c == ",":
            if inner[begin:i].strip():
                out.append((start + 1 + begin, start + 1 + i))
            begin = i + 1
    return out


def without(text: str, items: list[tuple[int, int]], k: int) -> tuple[int, int]:
    """The span to delete to drop element k of a list or table: the element
    and the comma after it, or before it when it is the last."""
    a, z = items[k]
    if k + 1 < len(items):
        return a, items[k + 1][0]
    if k:
        return text.rindex(",", items[k - 1][1], a), z
    return a, z


def binding_edits(binds: runsc.Bindings) -> list[Edit]:
    made = binds.made_names()
    out: list[Edit] = []
    for path in sorted(runsc.BINDINGS.glob("*.toml")):
        name, text = path.name, path.read_text()
        out += key_edits(name, text)
        shapes = {}
        for kind, a, z, *items in values(text):
            if kind == "string":
                s = text[a + 1:z - 1]
                shapes.setdefault("." in s, set()).add(s)
        for kind, a, z, *items in values(text):
            where = f"{name}:{text.count(chr(10), 0, a) + 1}"
            if kind in ("list", "table"):
                elements = items[0] if kind == "list" else table_entries(text, a, z)
                for k, (x, y) in enumerate(elements):
                    lo, hi = without(text, elements, k)
                    out.append(Edit(f"{where} drop {text[x:y].strip()}", "element", name, lo, hi))
            elif kind == "string":
                s = text[a + 1:z - 1]
                for o in sorted(shapes["." in s] - {s}):
                    out.append(Edit(f"{where} {s} -> {o}", "value", name, a, z, f'"{o}"', s in made))
            elif kind == "number":
                v = int(text[a:z], 0)
                for o in {v + 1, max(v - 1, 0)} - {v}:
                    out.append(Edit(f"{where} {v} -> {o}", "value", name, a, z, oct(o) if text[a:z].startswith("0o")
                                    else str(o)))
            else:
                out.append(Edit(f"{where} {text[a:z]} flipped", "value", name, a, z,
                                "false" if text[a:z] == "true" else "true"))
    return out


def edited(e: Edit) -> tuple[str, str]:
    """A binding mutant must build another image or be refused: one that
    builds the image is dead, unless it only renames a C word."""
    home = runsc.BINDINGS
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(home, tmp / "pdp1")
        text = (tmp / "pdp1" / e.file).read_text()
        (tmp / "pdp1" / e.file).write_text(text[:e.start] + e.new + text[e.end:])
        runsc.BINDINGS = tmp / "pdp1"
        try:
            if runsc.build(program(), tmp / "out"):
                return "changed", ""
            return ("renamed" if e.renames else "dead"), ""
        except (runsc.BindError, tomllib.TOMLDecodeError) as x:
            return "refused", str(x)
        except Exception as x:      # noqa: BLE001 - a crash is a finding of the gate
            return "crash", f"{type(x).__name__}: {x}"
        finally:
            runsc.BINDINGS = home


# ---------------------------------------------------------------- the gate

PROGRAM: list[runs.Program] = []


def program() -> runs.Program:
    if not PROGRAM:
        PROGRAM.append(runsc.pdp1_program())
    return PROGRAM[0]


def verdict(m: Mutant) -> tuple[str, str]:
    """changed, rejected (by the evaluator), refused (by runsc), equivalent,
    precondition, bound, or the failures: silent, crash."""
    prog = program()
    mutated = mutate(prog, m)
    try:
        runs.check(mutated)
    except runs.RunsError as e:
        return "rejected", str(e)
    if is_bound(prog, m):
        ok, how = bounded(prog, mutated, m)
        return ("bound" if ok else "silent"), how
    with tempfile.TemporaryDirectory() as out:
        try:
            code = runsc.build(mutated, Path(out))
        except runsc.BindError as e:
            return "refused", str(e)
        except Exception as e:      # noqa: BLE001 - a crash is a finding of the gate
            return "crash", f"{type(e).__name__}: {e}"
    if code != 0:
        return "changed", next((s.strip() for s in runsc.build.said.splitlines() if "first difference" in s), "")
    if m.kind == "requires":
        ok, how = precondition(prog, mutated, m)
        return ("precondition" if ok else "silent"), how
    ok, how = equivalent(prog, mutated, m)
    return ("equivalent" if ok else "silent"), how


OUTCOMES = ("changed", "refused", "rejected", "equivalent", "precondition", "bound", "renamed", "silent", "dead",
            "crash")
FAILURES = ("silent", "dead", "crash")


def main() -> int:
    prog = program()
    with tempfile.TemporaryDirectory() as out:      # not build/runs: the other checks read it meanwhile
        code = runsc.build(prog, Path(out))
    if code != 0:
        print(runsc.build.said)
        print("check_compiled: the unmutated image does not match")
        return 1
    built: list = sites(prog)
    played(prog)                # once, before the workers fork
    built += binding_edits(runsc.Bindings(prog, sorted(runsc.BINDINGS.glob("*.toml"))))
    if "--kinds" in sys.argv:
        kinds = sys.argv[sys.argv.index("--kinds") + 1].split(",")
        built = [m for m in built if m.kind in kinds]
    if "--only" in sys.argv:
        built = [m for m in built if sys.argv[sys.argv.index("--only") + 1] in m.label]
    if "--sample" in sys.argv:
        n = int(sys.argv[sys.argv.index("--sample") + 1])
        random.Random(1962).shuffle(built)
        built = built[:n]
    with ProcessPoolExecutor(mp_context=multiprocessing.get_context("fork")) as pool:
        results = list(pool.map(judge, built, chunksize=4))
    by = Counter()
    for m, (what, how) in zip(built, results):
        by[(m.kind, what)] += 1
        if what in FAILURES + ("equivalent", "precondition", "bound"):
            print(f"  {what.upper() if what in FAILURES else what}: {m.label}: {how[:160]}")
    for kind in sorted({k for k, _ in by}):
        print(f"  {kind}: " + ", ".join(f"{by[(kind, w)]} {w}" for w in OUTCOMES if by[(kind, w)]))
    total = Counter(w for w, _ in results)
    failed = sum(total[w] for w in FAILURES)
    print(f"check_compiled: image matches; {len(built)} mutants{' (sampled)' if '--sample' in sys.argv else ''}: "
          + ", ".join(f"{total[w]} {w}" for w in OUTCOMES))
    return 1 if failed else 0


def judge(m) -> tuple[str, str]:
    return edited(m) if isinstance(m, Edit) else verdict(m)


if __name__ == "__main__":
    sys.exit(main())
