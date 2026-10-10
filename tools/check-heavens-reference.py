"""G1 for the heavens (lift/heavens.c): the native build against SIMH
running the oracle binary.

- The star catalog: every word of the four magnitude tables, native,
  against the words SIMH loads from the oracle image at 06077.
- The central star (blp): calls in a row from several seeds of the random
  number generator, sense switches varied per call. After each call: the
  random number, the slope words bx and by, the jump into the line (bjm),
  and every point plotted, in order.
- The Expensive Planetarium (bck): frames in a row, enough for the window
  to go once round the sky (sense switch 4 off), then frames that each set
  the right margin to a random place first, sense switches varied per call. After each frame: the frame
  and window counters, the right margin, each magnitude's cursor, scan
  start and the two home instructions that hold its star pointers, and
  every point plotted, in order.

Both routines drive the display, and SIMH has none: a breakpoint on each
display instruction reports AC and IO there, and the native pdp1.h records
each point it is asked to plot. A routine's AC and IO at return are not
compared; neither routine returns a value.

Usage: uv run python tools/check-heavens-reference.py"""
import subprocess
import sys
from pathlib import Path

from oracle_check import ROOT, built_symbols, seeded
from pdp1cc import dialect, front, inline, ir, splice
from pdp1cc.gate import corpus, reference, simh
from pdp1cc.gate.simh import Inputs

LIFT = ["lift/tunables.c", "lift/heavens.c"]
TABLES = ["first_magnitude", "second_magnitude", "third_magnitude", "fourth_magnitude"]
SET = 1                     # a call whose AC input is SET first sets the routine's state from IO
SEEDS = [0, 0o225241, 0o123456, 0o777777]
STAR_CALLS = 25000          # central star calls per seed
SENSE_4 = 0o04              # sense switch 4 turns the heavens off
WALK_FRAMES = 2 * 16 * 0o20000 + 1000  # the window moves once in 32 frames: once round the sky
JUMP_FRAMES = 20000         # Planetarium frames from a random right margin each


def units():
    _, regions = splice.load(ROOT / "lift.toml")
    prefix = {r.c.resolve(): r.prefix for r in regions}
    return {f: dialect.lower_unit(front.parse(ROOT / f), prefix[(ROOT / f).resolve()]) for f in LIFT}


def native(name: str, call: str, watch: list[str], placed, us, setup: str = "") -> Path:
    """Build a driver that reads `ac io byname sense` per line, runs call,
    and prints `0 0 0`, the watched words, `;` and the plotted points."""
    out = ROOT / "build/ref" / name
    src = out.parent / f"{name}-src"
    src.mkdir(parents=True, exist_ok=True)
    driver = src / "driver.cpp"
    driver.write_text(
        reference.symbol_table(placed) +
        "#include <cstdio>\nint main() {\n    unsigned ac, io, byname, sense;\n"
        "    while (std::scanf(\"%o %o %o %o\", &ac, &io, &byname, &sense) == 4) {\n"
        f"        pdp1_sense_switches = sense;\n        pdp1_plotted.clear();\n{setup}"
        f"        {call};\n        std::printf(\"0 0 0\");\n"
        + "".join(f"        std::printf(\" %06o\", pdp1_value({w}));\n" for w in watch) +
        "        std::printf(\" ;\");\n"
        "        for (const pdp1_point &p : pdp1_plotted)\n"
        "            std::printf(\" %06o %06o %06o\", p.instruction, p.x, p.y);\n"
        "        std::printf(\"\\n\");\n    }\n    return 0;\n}\n")
    stubs = src / "stubs.h"
    sigs = {n: s for u in us.values() for n, s in u.signatures.items()}
    defined = {f.sig.name for u in us.values() for f in u.items if isinstance(f, ir.Function)}
    defined |= {name for u in us.values() for name in u.inlines}
    stubs.write_text("".join(reference.stub(s) for n, s in sigs.items() if n not in defined))
    subprocess.run(["g++", "-std=c++14", "-O2", "-Wall", "-Wno-register", "-Wno-unused-label",
                    "-Wno-array-bounds", "-Werror", "-include", str(reference.HEADER),
                    *[a for f in LIFT for a in ("-include", str(ROOT / f))],
                    "-include", str(stubs), str(driver), "-o", str(out)], check=True)
    return out


def home(opcode: int, pointer: str, table: str) -> str:
    """A home instruction's word, natively. The pointer walks table and can
    stop one past its end; its address is reckoned from the table, since a
    host object that happens to follow the table would claim that pointer."""
    return (f"word::bits(0{opcode:o} | ({pointer} ? (pdp1_address({table}) + "
            f"(unsigned)({pointer} - {table})) & PDP1_ADDR : 0u))")


def compare(label: str, calls, want, got, names: list[str]) -> int:
    diffs = []
    for n, (c, w, g) in enumerate(zip(calls, want, got)):
        bad = [f"{k} simh {a:06o} native {b:06o}" for k, a, b in zip(names, w.watched, g.watched) if a != b]
        if w.plotted != g.plotted:
            k = next((k for k, (a, b) in enumerate(zip(w.plotted, g.plotted)) if a != b),
                     min(len(w.plotted), len(g.plotted)))
            bad.append(f"plotted {len(w.plotted)} simh, {len(g.plotted)} native, first differing point {k}")
        if bad:
            diffs.append(f"call {n} (sense {c.sense:02o}): " + ", ".join(bad))
    if len(want) != len(got):
        diffs.append(f"{len(want)} simh results, {len(got)} native")
    points = sum(len(w.plotted) for w in want)
    print(f"{label}: {len(calls)} calls, {len(calls) - len(diffs)} match, {len(diffs)} differ; "
          f"{points} points plotted, {len(names)} words compared after each")
    for d in diffs[:10]:
        print("  " + d[:300])
    return 1 if diffs else 0


def catalog(address: dict[str, int], us) -> int:
    """Every word of the catalog: native table against the oracle image."""
    u = us["lift/heavens.c"]
    words = [(t, k) for t in TABLES for k in range(u.words(t))]
    first = address[u.objects[TABLES[0]].sym]
    script = f"load {ROOT / 'build/oracle.rim'}\nex {first:o}-{first + len(words) - 1:o}\nquit\n"
    out = subprocess.run([str(ROOT / "build/pdp1")], input=script, capture_output=True, text=True).stdout
    image = [int(m.group(2), 8) for line in out.splitlines() if (m := simh.EXAMINE.match(line))]
    binary = native("catalog", "(void)0", [f"{t}[{k}]" for t, k in words], [], us)
    got = reference.run(binary, [Inputs(0)])[0].watched
    diffs = [(t, k, a, b) for (t, k), a, b in zip(words, image, got) if a != b]
    same = sum(a == b for a, b in zip(image, got))
    print(f"star catalog: {len(words)} native words, {len(image)} read from the oracle image at "
          f"{first:05o}; {same} match, {len(diffs)} differ")
    for t, k, a, b in diffs[:10]:
        print(f"  {t}[{k}]: oracle {a:06o} native {b:06o}")
    return 1 if diffs or len(image) != len(words) else 0


def main() -> int:
    address = built_symbols()
    us = units()
    heavens = us["lift/heavens.c"]
    placed = [p for u in us.values() for p in reference.placements(u, address)]
    display = corpus.display_words(ROOT / "build/lift/spliced.lst")
    failed = catalog(address, us)

    obj = heavens.objects
    sym = lambda name: address[obj[name].sym]
    duff = next(n for f in heavens.items if isinstance(f, ir.Function)
                for n in inline.iter_nodes(f.body) if isinstance(n, ir.HomedSwitch))
    jump = f"word::bits(0600000 | (0{address[duff.table]:o}u + 8u * line_dots_skipped.v))"
    star_watch = [("ran", address["ran"], "random_number"), ("bx", sym("slope_x"), "slope_x"),
                  ("by", sym("slope_y"), "slope_y"),
                  ("bjm", address[duff.index.storage.sym], jump)]
    star = native("central_star", "central_star()", [w for *_, w in star_watch], placed, us,
                  f"        if (ac == {SET}) random_number = word::bits(io);\n")
    for n, seed in enumerate(SEEDS):
        senses = [s & 0o77 for s in seeded(100 + n, STAR_CALLS)]
        senses[0] &= ~0o01          # switch 6 off: the first call draws, so bjm holds a case
        calls = [Inputs(SET if k == 0 else 0, seed if k == 0 else 0, 0, s) for k, s in enumerate(senses)]
        want = simh.run_jda(ROOT / "build/pdp1", ROOT / "build/oracle.rim", address["blp"], calls,
                            watch=[a for _, a, _ in star_watch], op="jsp", display=display,
                            deposits={address["ran"]: seed})
        got = reference.run(star, calls)
        failed |= compare(f"central star from ran {seed:06o}", calls, want, got,
                          [k for k, *_ in star_watch])

    sky_watch = [("bcc", sym("alternate_frames"), "alternate_frames"),
                 ("bkc", sym("window_steps"), "window_steps"),
                 ("fpr", sym("right_margin"), "right_margin")]
    for m, table in enumerate(TABLES, 1):
        sky_watch += [(f"flo{m}", sym(f"cursor{m}"), f"cursor{m}"),
                      (f"fpo{m}", sym(f"scan_start{m}"), f"scan_start{m}"),
                      (f"fin{m}", address[obj[f"star_x{m}"].sym], home(0o200000, f"star_x{m}", table)),
                      (f"fyn{m}", address[obj[f"star_y{m}"].sym], home(0o220000, f"star_y{m}", table))]
    sky = native("expensive_planetarium", "expensive_planetarium()", [w for *_, w in sky_watch],
                 placed, us, f"        if (ac == {SET}) right_margin = word::bits(io);\n")
    walk = [Inputs(0, 0, 0, s & 0o77 & ~SENSE_4) for s in seeded(200, WALK_FRAMES)]
    jumps = [Inputs(SET, m & 0o17777, 0, s & 0o77)
             for m, s in zip(seeded(300, JUMP_FRAMES), seeded(301, JUMP_FRAMES))]
    for label, calls in (("frames in a row", walk), ("frames from a random right margin", jumps)):
        each = [{sym("right_margin"): c.io} if c.ac == SET else {} for c in calls]
        want = simh.run_jda(ROOT / "build/pdp1", ROOT / "build/oracle.rim", address["bck"], calls,
                            watch=[a for _, a, _ in sky_watch], op="jsp", display=display, each=each)
        got = reference.run(sky, calls)
        failed |= compare(f"Expensive Planetarium, {label}", calls, want, got,
                          [k for k, *_ in sky_watch])
        print(f"  {len({w.watched[2] for w in want})} distinct right margins after a frame")
    return failed


if __name__ == "__main__":
    sys.exit(main())
