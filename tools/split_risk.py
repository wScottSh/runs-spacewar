"""Where splitting each game Processor puts work on the compiler.

For each cut between two top-level statements of a body: does a local set
before it get read after it? Split there, that value goes from one piece
to the next through a field the Network wires, where the original kept it
in a register, and runsc must lower the field back to the register. Also
counted: control flow in the body, and declaration entries naming the
Processor (a split must keep what they name). Nested cuts are only seen
through the control-flow count.

Read-only. Usage: PYTHONPATH=tools uv run -q python tools/split_risk.py"""
import re, sys
from collections import defaultdict
from pathlib import Path
import runs
from audit_shapes import unit_of, walk

CTRL = {"if", "loop", "for", "match", "break", "return", "jump", "continue"}

def names(x, out):
    if isinstance(x, tuple):
        if len(x) == 2 and x[0] == "name" and isinstance(x[1], str):
            out.add(x[1]); return out
        for y in x: names(y, out)
    elif isinstance(x, (list,)):
        for y in x: names(y, out)
    elif isinstance(x, dict):
        for y in x.values(): names(y, out)
    return out

def defs(st):
    d = set()
    for s in walk([st]):
        if s[0] == "let":
            names(s[1], d)
        if s[0] == "for":
            d.add(s[1])
    return d

root = runs.source()
prog = runs.check(runs.load(sorted(root.glob("*.runs")) + sorted(root.glob("*.runs-prim"))), sides=False)
unit = unit_of(root)
shown = runs.presentation_routines(prog)
game = [n for n, r in prog.routines.items() if r.kind == "processor" and n not in shown]
decl = "\n".join(p.read_text() for p in sorted(Path("pdp1").glob("*.toml")))

rows = []
for n in game:
    body = prog.routines[n].body
    locals_ = set()
    for st in body: locals_ |= defs(st)
    cuts = len(body) - 1
    handed = 0
    for i in range(1, len(body)):
        before = set().union(*(defs(s) for s in body[:i])) if i else set()
        after = names(body[i:], set())
        if before & after & locals_:
            handed += 1
    ctrl = sum(1 for s in walk(body) if s[0] in CTRL)
    nd = len(re.findall(rf"(?m)^(?!\s*#).*(\"{n}\"|\[[^\]]*\b{n}\b[^\]]*\])", decl))
    rows.append((unit[n], n, len(list(walk(body))), cuts, handed, ctrl, nd))

tot = defaultdict(lambda: [0]*6)
for u, n, *v in rows:
    t = tot[u]; t[0] += 1
    for k, x in enumerate(v): t[k+1] += x
print(f"{'unit':12} procs stmts cuts handed ctrl decl")
for u, t in sorted(tot.items()):
    print(f"{u:12} {t[0]:5} {t[1]:5} {t[2]:4} {t[3]:6} {t[4]:4} {t[5]:4}")
print()
print(f"{'processor':28} {'unit':11} stmts cuts handed ctrl decl")
for u, n, *v in sorted(rows, key=lambda r: (r[0], -r[4], r[1])):
    print(f"{n:28} {u:11} " + " ".join(f"{x:5}" for x in v))
