"""The program runsc compiles holds what its source says. The PDP-1
lowering (runsc.pdp1_program) puts each place of a network file in the
word the original keeps it in, and the evaluator runs that lowered RUNS
too (check_compiled judges mutants by it). After each firing of a network
file, each Record field its arcs write must hold the value runs.load's own
lowering (every place its own field) gives it from the same Records.

The compiled program plays games from power-on (check_compiled.games).
At each firing of a network file, the Records it starts from are handed to
the source's own lowering of that network file, its inputs set from the
wiring of the run; then every field the file's arcs write is compared.

Every field that differs is listed. --at-most N passes while no more
than N differ: the fields the lowering still keeps in a slot of a
collection, in an input or output of a network file laid out inline, or
in a counter a loop laid out inline counts in place; N only goes down.

Usage: [GAMES [FRAMES]] [--at-most N] (default 4 games of 20 frames)."""
from __future__ import annotations

import random
import sys

import check_compiled
import runs
import runsc


def written(g) -> list[tuple[str, str]]:
    """The Record fields g's arcs write: no input or output of g, no whole
    Record, no slot of a collection."""
    return sorted({tuple(a.place.split(".")) for a in g.arcs if not a.into and not g.port(a.place)
                   and not g.whole(a.place) and "." in a.place and "[" not in a.place})


def main() -> int:
    args = sys.argv[1:]
    most = int(args.pop(args.index("--at-most") + 1)) if "--at-most" in args else 0
    args = [a for a in args if a != "--at-most"]
    games = int(args[0]) if args else 4
    frames = int(args[1]) if len(args) > 1 else 20
    plain = runs.program(runs.source())
    compiled = runsc.pdp1_program()
    fields = {n: f for n, g in plain.graphs.items() if (f := written(g))}
    wrong: dict[str, str] = {}
    fired = compared = 0

    class Compared(runs.Machine):
        def run(self, name, args=()):
            nonlocal fired, compared
            template, wires = compiled.copies.get(name, (name, ()))
            if template not in fields:
                return super().run(name, args)
            source = runs.Machine(plain)
            for rec in source.state:
                if rec in self.state:
                    source.state[rec] = check_compiled.copied({rec: self.state[rec]})[rec]
            r = compiled.routines[name]
            scope = runs.Scope(r.kind, dict(zip(r.params, args)), r)
            for port, e in wires:
                if (c := plain.records.get(f"{template}_call")) and port in c.fields:
                    source.state[c.name][port] = self.eval(e, scope)
            fired += 1
            super().run(name, args)
            try:
                source.run(template, [scope.locals[p] for p in plain.routines[template].params])
            except (runs.RunsError, runs.Stop) as e:
                wrong.setdefault(f"{template}: the source's own lowering", f"stops: {e}")
                return
            compared += 1
            for rec, fld in fields[template]:
                want, got = source.state[rec][fld], self.state[rec][fld]
                if want != got:
                    wrong.setdefault(f"{rec}.{fld}", f"{template} writes {want}, the compiled RUNS leaves {got}")

    for x in check_compiled.games(compiled, Compared, random.Random(1962), range(games), frames):
        if isinstance(x, str):
            wrong.setdefault("the game", f"stops: {x}")
    for f, how in sorted(wrong.items()):
        print(f"  {f}: {how}")
    total = sum(map(len, fields.values()))
    print(f"check_fields: {total} fields the arcs of {len(fields)} network files write, {compared} of {fired} "
          f"firings compared, {len(wrong)} differ" + ("" if wrong else ": each holds what its arcs write"))
    return 1 if len(wrong) > most or "the game" in wrong or not compared else 0


if __name__ == "__main__":
    sys.exit(main())
