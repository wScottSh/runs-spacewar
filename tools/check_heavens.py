"""The heavens of heavens.runs against SIMH running the oracle image: the
Networks central_star (blp) and expensive_planetarium (bck), called as the
main loop calls them (jsp), after check-heavens-reference.py.

- The central star: calls from random numbers in a row and from a random
  number set first, with the sense switches varied. After each call: the
  random number, the slope words bx and by, the jump into the line (bjm,
  where draw_star's `skipped` lives), program flag 6 (its `half`), and
  every point plotted, in order.
- The Expensive Planetarium: frames in a row from the tape's words, then
  frames that each set the frame and window counters, the right margin
  and each magnitude's cursor first, with the sense switches varied. The
  margins and cursors include the edges: a window that straddles the
  sky's wrap, cursors on a magnitude's last star, windows with no star in
  them, so that scans go all the way round. After each frame: the
  counters, the margin, each magnitude's cursor and the words
  show_magnitude keeps its locals in (the scan start, fpo, and the homes
  of star_x and star_y, fin and fyn), program flag 5 (`scan`), and every
  point plotted, in order.

The check counts how often each statement of the heavens' Processors runs,
and fails if one never does: every path, the scan-wrap paths included, is
compared with SIMH.

Usage: [N] (calls of each kind, default 3000)."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import check_spaceship as ship
import pdp1
import runs
from oracle_check import built_listing
from pdp1cc.gate import corpus, simh
from pdp1cc.gate.simh import Inputs

PROCESSORS = ["star_slope", "draw_star", "count_frames", "skip_a_frame", "show_magnitude", "count_steps",
              "move_window"]
MAGNITUDES = [(0, 0o22, 3), (0o22, 0o44, 2), (0o44, 0o306, 1), (0o306, 0o1652, 0)]
LAC, LIO, JMP = 0o200000, 0o220000, 0o600000
NEG = lambda v: v ^ runs.MASK


def flag(pf: int, n: int) -> bool:
    return bool(pf >> (6 - n) & 1)


def console(m: runs.Machine, sense: int):
    for name, n in pdp1.SWITCHES.items():
        m.state["console"][name] = runs.Member("switch", "on" if sense >> (6 - n) & 1 else "off")


class Coverage:
    """How often each statement of the heavens' Processors runs."""

    def __init__(self, m: runs.Machine):
        self.lines = {s[-1]: 0 for name in PROCESSORS for s in statements(m.prog.routines[name].body)}
        plain = m.stmt

        def counted(s, scope):
            if s[-1] in self.lines:
                self.lines[s[-1]] += 1
            return plain(s, scope)
        m.stmt = counted

    def never(self) -> list[str]:
        return [where for where, n in self.lines.items() if n == 0]


def statements(stmts):
    for s in stmts:
        yield s
        if s[0] == "if":
            for _, body in s[1]:
                yield from statements(body)
            yield from statements(s[2])
        elif s[0] in ("loop", "for"):
            yield from statements(s[-2])


def points(outcome) -> list:
    return [pdp1.point(p) for p in outcome.plotted]


def central_star(m: runs.Machine, sym: dict, display: dict, n: int, rng: random.Random) -> tuple[int, int]:
    cases = []
    for k in range(n):
        seed = rng.randrange(1 << 18) if k == 0 or rng.random() < 0.5 else None
        sense = rng.randrange(1 << 6)
        if rng.random() < 0.75:
            sense &= ~1                                     # switch 6 off: the star draws
        cases.append((seed, sense))
    watch = [sym["ran"], sym["bx"], sym["by"], sym["bjm"], "PF"]
    want = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym["blp"], [Inputs(0, 0, 0, s) for _, s in cases],
                        watch=watch, op="jsp", display=display,
                        each=[{sym["ran"]: seed} if seed is not None else {} for seed, _ in cases])
    differ = drawn = 0
    for k, ((seed, sense), w) in enumerate(zip(cases, want)):
        if seed is not None:
            m.state["random"]["number"] = runs.W(seed)
        console(m, sense)
        m.state["display"] = []
        m.left.pop(("draw_star", ()), None)
        m.run("central_star")
        ran, bx, by, bjm, pf = w.watched
        bad = []
        if ran != m.state["random"]["number"].v:
            bad.append(f"ran simh {ran:06o} runs {m.state['random']['number'].v:06o}")
        for name, got in (("slope_x", bx), ("slope_y", by)):
            if got != m.state["central_star"][name].v:
                bad.append(f"{name} simh {got:06o} runs {m.state['central_star'][name].v:06o}")
        left = m.left.get(("draw_star", ()))
        if left is not None:
            drawn += 1
            if bjm != JMP | sym["bds"] + 8 * left["skipped"].v:
                bad.append(f"bjm simh {bjm:06o} runs skipped {left['skipped'].v}")
            if flag(pf, 6) != (left["half"].name == "mirrored"):
                bad.append(f"flag 6 simh {flag(pf, 6)} runs {left['half'].name}")
        if points(w) != m.state["display"]:
            bad.append(f"plotted {len(w.plotted)} simh, {len(m.state['display'])} runs")
        if bad:
            differ += 1
            if differ <= 5:
                print(f"  central star call {k} (sense {sense:02o}): " + "; ".join(bad))
    print(f"central star: {n} calls, {n - differ} match, {differ} differ; {drawn} drew the star, "
          f"{sum(len(w.plotted) for w in want)} points")
    return differ, n


def a_frame(rng: random.Random) -> dict:
    """The planetarium's words set before a frame: the counters near where
    they run out, a right margin (some at the sky's wrap, where the window
    straddles it), and each magnitude's cursor (some on its last star)."""
    margin = rng.choice([rng.randrange(0o20000), rng.randrange(0o20000), rng.randrange(0o2000),
                         rng.randrange(0o16000, 0o20000), rng.choice([0, 1, 0o1777, 0o2000, 0o2001, 0o17777,
                                                                     0o10000, 0o16000])])
    cursors = []
    for first, past, _ in MAGNITUDES:
        stars = (past - first) // 2
        cursors.append(first + 2 * rng.choice([rng.randrange(stars), stars - 1, 0]))
    return {"alternate_frames": NEG(rng.choice([1, 1, 1, 0, 2])) if rng.random() < 0.9 else rng.randrange(1 << 18),
            "window_steps": NEG(rng.choice([1, 1, 0, 2, 0o20])) if rng.random() < 0.9 else rng.randrange(1 << 18),
            "right_margin": margin, "cursors": cursors}


def planetarium(m: runs.Machine, b: pdp1.Binding, sym: dict, display: dict, words: list[dict],
                calls: list[tuple[dict | None, int]], label: str) -> tuple[int, int]:
    watch = [sym["bcc"], sym["bkc"], sym["fpr"]] + [w[k] for w in words for k in
                                                     ("cursor", "scan_start", "star_x", "star_y")] + ["PF"]
    each = []
    for frame, _ in calls:
        d = {}
        if frame is not None:
            d = {sym["bcc"]: frame["alternate_frames"], sym["bkc"]: frame["window_steps"],
                 sym["fpr"]: frame["right_margin"]}
            d |= {w["cursor"]: b.encode("magnitudes", "cursor", runs.W(c)) for w, c in zip(words, frame["cursors"])}
        each.append(d)
    want = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym["bck"], [Inputs(0, 0, 0, s) for _, s in calls],
                        watch=watch, op="jsp", display=display, each=each)
    catalog = b.address("star_catalog", "words", 0)
    differ = drew = 0
    for k, ((frame, sense), w) in enumerate(zip(calls, want)):
        p = m.state["planetarium"]
        if frame is not None:
            for f in ("alternate_frames", "window_steps", "right_margin"):
                p[f] = runs.W(frame[f])
            m.state["magnitudes"]["cursor"] = [runs.W(c) for c in frame["cursors"]]
        console(m, sense)
        m.state["display"] = []
        for key in [key for key in m.left if key[0] == "show_magnitude"]:
            del m.left[key]
        m.run("expensive_planetarium")
        got = dict(zip(watch, w.watched))
        bad = []
        for f, s in (("alternate_frames", "bcc"), ("window_steps", "bkc"), ("right_margin", "fpr")):
            if got[sym[s]] != p[f].v:
                bad.append(f"{f} simh {got[sym[s]]:06o} runs {p[f].v:06o}")
        last = None
        for n, (wd, (first, past, intensity)) in enumerate(zip(words, MAGNITUDES)):
            cursor = m.state["magnitudes"]["cursor"][n]
            if got[wd["cursor"]] != b.encode("magnitudes", "cursor", cursor):
                bad.append(f"cursor {n} simh {got[wd['cursor']]:06o} runs {cursor.v:o}")
            left = m.left.get(("show_magnitude", tuple(runs.word_of(x) for x in (n, first, past, intensity))))
            if left is None:
                continue
            last = left
            for name, op in (("scan_start", LIO), ("star_x", LAC), ("star_y", LIO)):
                if got[wd[name]] != op | catalog + left[name].v:
                    bad.append(f"magnitude {n} {name} simh {got[wd[name]]:06o} runs {left[name].v:o}")
        if last is not None:
            drew += 1
            if flag(got["PF"], 5) != (last["scan"].name == "plotted"):
                bad.append(f"flag 5 simh {flag(got['PF'], 5)} runs {last['scan'].name}")
        if points(w) != m.state["display"]:
            bad.append(f"plotted {len(w.plotted)} simh, {len(m.state['display'])} runs")
        if bad:
            differ += 1
            if differ <= 5:
                print(f"  {label} frame {k} (sense {sense:02o}): " + "; ".join(bad)[:500])
    print(f"Expensive Planetarium, {label}: {len(calls)} frames, {len(calls) - differ} match, {differ} differ; "
          f"{drew} drew, {sum(len(w.plotted) for w in want)} points, "
          f"{len({w.watched[2] for w in want})} right margins after a frame")
    return differ, len(calls)


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    prog = runs.program(runs.source())
    b = pdp1.Binding(prog)
    sym = b.sym
    image = ship.image_words()
    words = pdp1.magnitude_words(sym, image)
    for slot, w in enumerate(words):
        b.slot_at[("magnitudes", "cursor", slot)] = w["cursor"]
    display = corpus.display_words(built_listing())
    m = runs.Machine(prog)
    cover = Coverage(m)
    rng = random.Random(0o1443)
    failed = 0
    differ, _ = central_star(m, sym, display, n, rng)
    failed |= bool(differ)
    m = runs.Machine(prog)
    cover_sky = Coverage(m)
    off = 1 << (6 - pdp1.SWITCHES["no_planetarium"])
    row = [(None, rng.randrange(1 << 6) & ~off if rng.random() < 0.95 else off) for _ in range(4 * n)]
    differ, _ = planetarium(m, b, sym, display, words, row, "frames in a row")
    failed |= bool(differ)
    set_first = [(a_frame(rng), rng.randrange(1 << 6) & ~off if rng.random() < 0.9 else off) for _ in range(n)]
    differ, _ = planetarium(m, b, sym, display, words, set_first, "frames from set words")
    failed |= bool(differ)
    never = [w for w, k in cover.lines.items() if k == 0 and cover_sky.lines[w] == 0]
    ran = sum(1 for w in cover.lines if cover.lines[w] + cover_sky.lines[w])
    print(f"coverage: {ran}/{len(cover.lines)} statements of the heavens' Processors ran")
    for where in never:
        print(f"  never ran: {Path(where.split(':')[0]).name}:{where.split(':')[1]}")
    return 1 if failed or never else 0


if __name__ == "__main__":
    sys.exit(main())
