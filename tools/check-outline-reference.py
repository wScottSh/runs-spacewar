"""G1 for the outline compiler (lift/outline_compiler.c, oc): the native
build against SIMH running oc in the oracle binary. The outline compiler is
not pure, but it is deterministic given its table: each call compiles one
outline table to CODE, and the comparison covers the returned end of the
compiled code (its extent), every word of the code area, the two jump
templates, the entry word, the outline pointer's home instruction, the
compiler's pool variables and the program flags. Natively the compiled code
is data the C wrote; nothing runs it.

Tables: the needle and wedge outlines (ot1, ot2) from the binary, and
synthetic tables, placed at TABLES, that use every direction code in every
position of a word, reach the 7 code as the first, a middle and the last
code of a word, and reach it after a store and after a restore (flag 6 left
set and clear).

Usage: uv run python tools/check-outline-reference.py"""
import sys

from oracle_check import ROOT, Inputs, built_symbols, lifted_signatures
from pdp1cc import dialect, front, ir, splice
from pdp1cc.gate import corpus, reference, simh

LIFT = ["lift/outline_compiler.c", "lift/outlines.c"]
CODE = 0o3772           # nnn: where the game compiles the outlines
AREA = 0o1000           # words of the code area compared after each call
TABLES = 0o5600         # free core below the star catalog

SYNTHETIC = {
    "every code, in order then reversed (one store)": [0o012345, 0o654321, 0o700000],
    "7 first in the outline": [0o700000],
    "7 in the middle of a word, later codes ignored": [0o123756],
    "7 as the last code of a word": [0o111111, 0o222227],
    "7 after a store (flag 6 left set)": [0o616161, 0o600000, 0o670000],
    "7 after a restore (flag 6 left clear)": [0o606000, 0o700000],
    "codes 0 and 1 interleaved, then 2..5 runs": [0o010101, 0o222333, 0o444555, 0o102345, 0o700000],
}


def main() -> int:
    files = [ROOT / f for f in LIFT]
    sigs = lifted_signatures(files)
    sig = sigs["outline_compiler"]
    address = built_symbols()
    _, regions = splice.load(ROOT / "lift.toml")
    prefix = {r.c.resolve(): r.prefix for r in regions}
    units = {f: dialect.lower_unit(front.parse(f), prefix[f.resolve()]) for f in files}
    placed = [p for u in units.values() for p in reference.placements(u, address)]

    tables, words = [], []
    for name, table in SYNTHETIC.items():
        tables.append((name, TABLES + len(words)))
        words += table
    placed.append(reference.Placement("&synthetic_tables", len(words), TABLES))
    placed.append(reference.Placement("&code_area", AREA + 1, CODE))
    scratch = (f"word synthetic_tables[{len(words)}] = {{{', '.join(f'0{w:o}' for w in words)}}};\n"
               f"word code_area[{AREA + 1}];\n")

    oc = units[files[0]]
    pool = [(n, s.sym) for n, s in oc.objects.items() if isinstance(s, ir.Pool) and s.sym in address]
    homed = [(n, s.sym) for n, s in oc.objects.items() if isinstance(s, ir.Homed)]
    templates = [(n, s.sym) for n, s in oc.objects.items() if n in oc.data]
    watch = [(f"code[{k:o}]", CODE + k, f"code_area[{k}]") for k in range(AREA)]
    watch += [(n, address[sym], n) for n, sym in pool + templates]
    watch += [(f"home of {n}", address[sym], f"I_LIO({n})") for n, sym in homed]
    watch += [("entry word", address[sig.sym], reference.cell(sig.name)),
              ("program flags", "PF", "word::bits(pdp1_program_flags)")]

    named = [("ot1", address["ot1"]), ("ot2", address["ot2"])] + tables
    calls = [Inputs(CODE, 0, table) for _, table in named]
    native = reference.build(files, sig, ROOT / "build/ref/outline_compiler",
                             [expr for *_, expr in watch], placed, scratch)
    want = simh.run_jda(ROOT / "build/pdp1", ROOT / "build/oracle.rim", address[sig.sym], calls,
                        watch=[where for _, where, _ in watch], inline=True,
                        deposits={TABLES + k: w for k, w in enumerate(words)})
    got = reference.run(native, calls)
    diffs = corpus.compare(calls, want, got, sig, [label for label, *_ in watch])
    for (name, _), w in zip(named, want):
        print(f"  {name:<48} compiled {w.ac - CODE:>4o} words (octal), flags {w.watched[-1]:02o}")
    print(f"outline compiler: {len(calls)} tables, {len(calls) - len(diffs)} match, "
          f"{len(diffs)} differ; {len(watch)} words compared after each")
    for d in diffs[:10]:
        print("  " + d[:400])
    return 1 if diffs or len(got) != len(calls) else 0


if __name__ == "__main__":
    sys.exit(main())
