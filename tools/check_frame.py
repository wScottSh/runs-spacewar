"""The frame Network of frame.runs against SIMH running the oracle image,
one whole frame from the frame seam (ml0) to its jump back there: the
restart checks, the whole object loop, collisions and calc routines
included, the spaceships', then the heavens and the spare time.

Each frame starts from one set of Records the game can hold. Most frames
have both ships flying; the restart delay starts low enough not to reach
0. Objects are bunched so that collisions happen. In SIMH the Records are
deposited where the PDP-1 binding places them, the compiled outlines are
laid out after the table (tools/check_spaceship.py), the frame's last
word, its jump back to ml0, is replaced by a jump to the stub's halt, and
the run enters at ml0.
The main loop itself loads each ship's outline into the jump at sp5, read
past the outline array for every other colliding object. The evaluator
fires the frame Network, the outlines its own outline compiler laid out
included. A full object table halts both, at the launch.

The central star's slope and the ship's gravity share two pool words (bx,
by), and program flag 6 is the star's mirror bit and the rocket's: each is
compared with whichever rule wrote it last in the frame.

The main loop loads ships.outline[slot] into sp5 for every colliding
object, so for a torpedo it reads past the 2-word array. With `poison`,
SIMH's main loop instead loads a jump to address 0 there for every slot
past the ships (an undefined instruction, which stops the machine): the
frames still match only if no ship ever jumps through a value read for
another slot. The RUNS frame never reads past the array.

`poison-all` poisons the ships' slots too, the control: SIMH must then stop.

Usage: [N] [poison|poison-all] (frames, default 1500)."""
from __future__ import annotations

import copy
import random
import sys

import check_heavens
import check_spaceship as ship
import pdp1
import runs
from pdp1cc.gate import corpus, simh
from pdp1cc.gate.simh import Inputs, STUB, CALL
from oracle_check import built_listing

RECORDS = ["objects", "ships", "random", "frame", "tunables", "spaceship", "pen", "planetarium", "magnitudes"]
NEG = lambda v: v ^ runs.MASK
JMP = 0o600000


def member(name: str) -> runs.Member:
    return runs.Member("calc_routine", name)


def near(rng: random.Random, centre: int, spread: int) -> runs.W:
    return runs.word_of(max(-0o377777, min(0o377777, centre + rng.randrange(-spread, spread))))


def a_frame(m: runs.Machine, rng: random.Random, outlines) -> tuple[dict, int]:
    st = copy.deepcopy({r: m.state[r] for r in RECORDS + ["console", "controls", "launch"]})
    o, sh = st["objects"], st["ships"]
    cx, cy = rng.randrange(-0o300000, 0o300000), rng.randrange(-0o300000, 0o300000)
    spread = rng.choice([0o4000, 0o20000, 0o100000, 0o400000])
    full = rng.random() < 0.02
    for s in range(0o30):
        ships = [("first_spaceship", "second_spaceship")[s % 2]] * 6 + ["explosion", "in_hyperspace", "breakout",
                                                                       "none"]
        o["routine"][s] = member(rng.choice(ships if s < 2 else ["torpedo", "explosion"] if full
                                            else ["none", "none", "torpedo", "torpedo", "explosion"]))
        o["x"][s], o["y"][s] = near(rng, cx, spread), near(rng, cy, spread)
        o["dx"][s], o["dy"][s] = runs.W(rng.randrange(1 << 18)), runs.W(rng.randrange(1 << 18))
        o["counter"][s] = runs.W(rng.choice([NEG(1), NEG(2), NEG(rng.randrange(1, 0o200)), 0, runs.MASK]))
        o["cycles"][s] = runs.W(rng.choice([0o20, 0o2000, 7, rng.randrange(0o4000)]))
    for s in range(2):
        for f in sh:
            sh[f][s] = runs.W(rng.randrange(1 << 18))
        sh["saved_routine"][s] = member(("first_spaceship", "second_spaceship")[s])
        sh["outline"][s] = runs.W(outlines.at[rng.choice(["needle", "wedge"])])
        sh["fuel"][s] = runs.W(rng.choice([NEG(rng.randrange(1, 0o20000)), 0, NEG(1), rng.randrange(1 << 18)]))
        sh["torpedoes"][s] = runs.W(rng.choice([NEG(rng.randrange(1, 0o41)), 0, rng.randrange(1 << 18)]))
        sh["previous_control"][s] = runs.W(rng.choice([0, 0, rng.randrange(1 << 18)]))
        if o["routine"][s].name.endswith("spaceship"):
            o["cycles"][s] = runs.W(rng.choice([0o2000, 0o2000, rng.randrange(1 << 18)]))
    for rec in ("spaceship", "pen"):
        for f, (typ, _) in m.prog.records[rec].fields.items():
            if typ == "word":
                st[rec][f] = runs.W(rng.randrange(1 << 18))
    outlines.b.share_one_word(st, ["spaceship", "pen"])
    st["launch"]["slot"] = runs.W(rng.randrange(0o30))
    sense = rng.randrange(1 << 6)
    for name, n in pdp1.SWITCHES.items():
        st["console"][name] = runs.Member("switch", "on" if sense >> (6 - n) & 1 else "off")
    st["controls"]["source"] = runs.Member("control_source", "test_word")
    st["console"]["test_word"] = runs.W(rng.randrange(1 << 18))
    st["console"]["control_boxes"] = runs.W(0)
    st["random"]["number"] = runs.W(rng.randrange(1 << 18))
    st["frame"]["restart_delay"] = runs.W(NEG(rng.randrange(2, 0o377777)))
    st["frame"]["objects_seen"] = runs.W(rng.randrange(1 << 18))
    st["frame"]["spare_time"] = runs.W(rng.randrange(1 << 18))
    sky = check_heavens.a_frame(rng)
    for f in ("alternate_frames", "window_steps", "right_margin"):
        st["planetarium"][f] = runs.W(sky[f])
    st["magnitudes"]["cursor"] = [runs.W(c) for c in sky["cursors"]]
    return st, sense


def poisoned(sym: dict, at: int, first: int = 2) -> dict[int, int]:
    """A patch of the main loop's outline read (mot, lac . / dap sp5): the
    dap jumps here instead. For a slot past the ships, sp5 becomes a jump
    to 0; for a ship, it takes the word read, as the original does. At
    `at`: the patch space (p), which no rule reads; the free core past the
    star catalog is SIMH's stub's."""
    mask, ships_end, bad, save = at + 0o20, at + 0o21, at + 0o22, at + 0o23
    words = [0o240000 | save,                       # dac save: the word mot read
             0o200000 | sym["ml1"],                 # lac ml1: the routine word's cursor
             0o020000 | mask,                       # and (7777
             0o420000 | ships_end,                  # sub (mtb+2
             0o640400,                              # sma: a ship's slot
             JMP | at + 0o11,
             0o200000 | save,
             0o260000 | sym["sp5"],                 # dap sp5
             JMP | sym["ml2"],
             0o200000 | bad,                        # lac (jmp 0
             0o240000 | sym["sp5"],                 # dac sp5
             JMP | sym["ml2"]]
    out = {at + k: w for k, w in enumerate(words)}
    return out | {mask: 0o7777, ships_end: sym["mtb"] + first, bad: JMP, sym["mot"] + 1: JMP | at}


def main() -> int:
    frames = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    poison = "poison" in sys.argv[2:] or "poison-all" in sys.argv[2:]
    alone = "alone" in sys.argv[2:]        # the game alone, every presentation routine removed, must fire the same
    first_poisoned = 0 if "poison-all" in sys.argv[2:] else 2      # poison-all: the control, ships too
    prog = runs.program(runs.source())
    b = pdp1.Binding(prog)
    sym = b.sym
    image = ship.image_words()
    for slot, w in enumerate(pdp1.magnitude_words(sym, image)):
        b.slot_at[("magnitudes", "cursor", slot)] = w["cursor"]
    end = next(a for a in range(sym["mq3"], sym["mq3"] + 0o10) if image[a] == JMP | sym["ml0"])
    m = runs.Machine(prog)
    outlines = ship.Outlines(m, b)
    full = sym["sr1"] + 6                                   # hlt: no space for new objects
    display = {a: w for a, w in (corpus.display_words(built_listing()) | outlines.display).items() if a != full}
    rng = random.Random(0o1444)
    cases = [a_frame(m, rng, outlines) for _ in range(frames)]
    places = list(b.places(RECORDS))
    halt, halt_full = STUB + 3, STUB + 4
    watch = [p[3] for p in places] + [sym["sr1"], "PF"]
    each = [b.deposits(st, RECORDS + ["controls"]) | {sym["sr1"]: image[sym["sr1"]] & ~0o7777 | sym["mtb"] + st["launch"]["slot"].v}
            for st, _ in cases]
    want = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, sym["ml0"],
                        [Inputs(0, 0, 0, sense, st["console"]["test_word"].v) for st, sense in cases],
                        watch=watch, op="jmp", display=display,
                        deposits=outlines.code | {end: JMP | halt, full: JMP | halt_full}
                        | (poisoned(sym, sym["p"], first_poisoned) if poison else {}), each=each)
    differ, fired, hits, halts = 0, {}, [0], 0
    game = runs.Machine(runs.without_presentation(prog)) if alone else None
    if game:                                # what the setup gave the whole program, the outlines included
        game.state.update({r: copy.deepcopy(m.state[r]) for r in game.state})
    plain_run = m.run

    def counted_run(name, args=()):
        before = list(m.state["objects"]["routine"])
        plain_run(name, args)
        if name == "collision" and m.state["objects"]["routine"] != before:
            hits[0] += 1
    m.run = counted_run
    for k, ((st, _), w) in enumerate(zip(cases, want)):
        m.state.update(copy.deepcopy(st))
        m.state["display"] = []
        m.fired = []
        halted = False
        since = m.writes
        try:
            m.run("frame")
        except runs.Stop:
            halted = True
        halts += halted
        values = dict(zip(watch, w.watched))
        apart = []
        if game:
            game.state.update({r: v for r, v in copy.deepcopy(st).items() if r in game.state})
            for r in game.prog.records.values():
                if r.stream:
                    game.state[r.name] = []
            try:
                game.run("frame")
                apart += ["the game alone halted where the whole program did not"] if halted else []
            except runs.Stop:
                apart += [] if halted else ["the game alone halted where the whole program did not"]
            except runs.RunsError as e:
                apart.append(f"the game alone fails: {str(e).split(': ', 1)[-1]}")
            apart += [f"the game alone differs in {r}" for r in game.prog.records
                      if game.state[r] != m.state[r]]
        simh_records = b.read({p[3]: values[p[3]] for p in places}, RECORDS)
        star = any(name == "star_slope" for name, _ in m.fired)
        shared = []
        if star:                                # bx and by hold what the star wrote last
            for f, g in (("gravity_x", "slope_x"), ("gravity_y", "slope_y")):
                if simh_records["spaceship"][f] != m.state["central_star"][g]:
                    shared.append(f"central_star.{g} simh {simh_records['spaceship'][f].v:06o} "
                                  f"runs {m.state['central_star'][g].v:06o}")
                simh_records["spaceship"][f] = m.state["spaceship"][f]
        get = lambda recs, rec, fld, s: recs[rec][fld] if s is None else recs[rec][fld][s]
        outlived = b.outlived(m, RECORDS, since)
        bad = [f"{rec}.{fld}{'' if s is None else f'[{s}]'} simh {b.encode(rec, fld, get(simh_records, rec, fld, s)):06o}"
               f" runs {b.encode(rec, fld, get(m.state, rec, fld, s)):06o}"
               for rec, fld, s, _ in places if (rec, fld) not in outlived
               and get(simh_records, rec, fld, s) != get(m.state, rec, fld, s)] + shared
        rocket = b.read_flags(values["PF"], ("spaceship",))["spaceship"]["rocket"]
        # SIMH's flags carry over from the frame before: compare flag 6 with
        # what last set it, the star's line (left mirrored) or a ship
        if star and rocket.name != "firing":
            bad.append("flag 6 clear after the star's mirrored half")
        elif not star and any(name == "steer" for name, _ in m.fired) and rocket != m.state["spaceship"]["rocket"]:
            bad.append(f"spaceship.rocket simh {rocket.name} runs {m.state['spaceship']['rocket'].name}")
        if (values[sym["sr1"]] & 0o7777) - sym["mtb"] != m.state["launch"]["slot"].v:
            bad.append("launch.slot differs")
        if (w.returned_past == halt_full - (CALL + 1)) != halted:
            bad.append(f"halted: simh {w.returned_past == halt_full - (CALL + 1)}, runs {halted}")
        points = [pdp1.point(p) for p in w.plotted]
        if points != m.state["display"]:
            bad.append(f"plotted {len(points)} simh, {len(m.state['display'])} runs")
        bad += apart
        if bad:
            differ += 1
            if differ <= 5:
                print(f"  frame {k}: " + "; ".join(bad)[:600])
        for name, _ in m.fired:
            fired[name] = fired.get(name, 0) + 1
    removed = sorted(set(prog.routines) - set(game.prog.routines)) if game else []
    if game:
        print(f"the game alone: {len(removed)} presentation routines removed, "
              f"{len(game.prog.records)} of {len(prog.records)} Records kept")
    print(f"frame{' (sp5 poisoned past the ships)' if poison else ''}{' (and the game alone)' if game else ''}: {len(cases)} frames, {len(cases) - differ} match, {differ} differ; "
          f"{sum(len(w.plotted) for w in want)} points, {halts} halted on a full table")
    print(f"  fired: {dict(sorted(fired.items()))}")
    print(f"  collisions that hit: {hits[0]}")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
