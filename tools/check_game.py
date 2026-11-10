"""The game control of frame.runs against SIMH running the oracle image: the
start Networks from power-on, and the frame's restart checks, scoring, the
match count, the halt between games and the new game.

Two kinds of run, each in one SIMH session:

1. Seeded cases. Each deposits a set of Records the game can hold and the
   console's test words, then enters at ml0 (a frame), or at 4 or 5 (the
   operator's start, with the power-on scores and game count random). It
   runs until the object loop (a breakpoint at ml1) or the jump back to ml0
   that ends a new game. A breakpoint on the halt between games records the
   scores on the lights, deposits the second test word and continues past
   the halt, as the operator does. The evaluator fires the same Network on
   the same Records, the second test word given at its wait.
2. the seventeen scripted matches (tools/check-main-loop-frames.py:
   the same scenarios and control policies), played from power-on. At each
   stop (a frame at ml0, or a halt) the evaluator takes SIMH's Records and
   the test word given for the run that follows, and fires the frame up to
   the object loop. When the game ends there, it fires on through the halt
   and the new game, and every Record must match SIMH's at the next frame;
   otherwise the restart delay must, and SIMH must not have reached the end
   of the game (a breakpoint at a).

The evaluator never runs the object loop here (tools/check_frame.py covers
it). A new game runs the RUNS outline compiler, so where each ship's
outline starts is compared too (tools/check_outline_compiler.py compares
the words it lays out).

Usage: [CASES] [STOPS] (seeded cases, default 3000; stops per scripted
match, default 3000; 0 skips that part)."""
from __future__ import annotations

import copy
import dataclasses
import importlib.util
import os
import random
import re
import sys
from concurrent.futures import ProcessPoolExecutor

import pdp1
import runs
from pdp1cc.gate import simh
from pdp1cc.gate.simh import Inputs

spec = importlib.util.spec_from_file_location("frames", pdp1.ROOT / "tools/check-main-loop-frames.py")
frames = importlib.util.module_from_spec(spec)
sys.modules["frames"] = frames
spec.loader.exec_module(frames)

RECORDS = ["objects", "ships", "random", "frame", "pacing", "tunables", "outline_setting", "score", "controls"]
# Fields the evaluator may hold unknown where SIMH holds a word: the lights,
# program flags 1 and 2, keep what the machine held at power-on until a game
# ends, and nothing in the game reads them. Any other field the evaluator
# does not know while SIMH does is a difference.
POWER_ON = {"lights.first_survived", "lights.second_survived"}
NEG = lambda v: v ^ runs.MASK
JMP = 0o600000
BREAK = re.compile(r"Breakpoint, PC: ([0-7]+)")
HALT = re.compile(r"HALT instruction, PC: ([0-7]+)")
EXAMINED = re.compile(r"^(AC|IO|PF|[0-7]+):\s+([0-7]+)$")


# The tunables the scripted matches patch: an operator's `law n` or `law i n`
# in the xct word is the house rule that sets the Processor's number.
TUNABLE_PROCESSORS = {"tno": "torpedo_supply", "rlt": "torpedo_reload_time", "tlf": "torpedo_life",
                      "mhs": "hyperspace_shots"}
LAW, LAW_I = 0o700000, 0o710000


def member(enum: str, name: str) -> runs.Member:
    return runs.Member(enum, name)


def house_rules(prog: runs.Program, deposits) -> runs.Program:
    """The program with each patched tunable's Processor edited to match."""
    routines = dict(prog.routines)
    for name, value in deposits:
        if name not in TUNABLE_PROCESSORS:
            continue
        if value & 0o770000 not in (LAW, LAW_I):
            raise ValueError(f"{name}: {value:06o} is not law n or law i n")
        n = ("num", value & 0o7777)
        r = routines[TUNABLE_PROCESSORS[name]]
        (op, target, _, where), = r.body
        new = ("neg", n) if value & 0o770000 == LAW_I else n
        routines[r.name] = runs.Routine(r.kind, r.name, r.params, [(op, target, new, where)],
                                        r.reads, r.writes, r.requires)
    return dataclasses.replace(prog, routines=routines)


@dataclasses.dataclass(frozen=True)
class CodeWord:
    """A word of SIMH's that holds a place in the outline's strokes: the
    address of the stroke's words. Where a slot lies depends on the strokes
    before it, so it is compared with the evaluator's slot laid out by the
    evaluator's strokes."""
    word: int


class Game:
    """The evaluator, the binding and SIMH's addresses for one session."""

    def __init__(self, deposits=()):
        self.prog = house_rules(runs.program(runs.source()), deposits)
        self.b = pdp1.Binding(self.prog)
        self.sym = self.b.sym
        self.places = list(self.b.places(RECORDS))
        self.halt = self.sym["a4"] + 2                      # lac \1sc / lio \2sc / hlt
        words = frames.read_listing(pdp1.ROOT / "build/oracle.lst")
        self.next_game = next(a for a in range(self.sym["a2"], self.sym["mg1"])
                              if words[a].value == JMP | self.sym["ml0"])

    def machine(self) -> runs.Machine:
        return runs.Machine(self.prog)

    def snapshot_command(self) -> str:
        return "ex " + ",".join(f"{p[3]:o}" for p in self.places) + ",PF,AC,IO"

    def decode(self, values: dict) -> dict:
        """SIMH's core as Records. A word no member spells (cwg before the
        start sets it) is unknown."""
        state: dict = {}
        for rec, fld, slot, at in self.places:
            try:
                v = CodeWord(values[at]) if pdp1.INTO.get((rec, fld)) == self.b.code \
                    else self.b.decode(rec, fld, values[at])
            except ValueError:
                v = runs.UNKNOWN
            if slot is None:
                state.setdefault(rec, {})[fld] = v
            else:
                state.setdefault(rec, {}).setdefault(fld, [None] * self.prog.records[rec].count)[slot] = v
        state.update(self.b.read_flags(values["PF"]))
        return state

    def differences(self, m: runs.Machine, simh_state: dict, only: list[str] | None = None) -> list[str]:
        bad = []
        for rec, recs in simh_state.items():
            for fld, want in recs.items():
                if only and f"{rec}.{fld}" not in only:
                    continue
                got = m.state[rec][fld]
                for s, (w, g) in enumerate(zip(want, got) if isinstance(want, list) else [(want, got)]):
                    if g is runs.UNKNOWN and (w is runs.UNKNOWN or f"{rec}.{fld}" in POWER_ON):
                        continue
                    if isinstance(w, CodeWord) and not isinstance(g, CodeWord):
                        # the strokes the evaluator's compiler laid out, before outline_call.code
                        kept = self.b.code_slots
                        self.b.lay_out_code(m.state["outline_code"], m.state["outline_call"]["code"].v)
                        g = CodeWord(self.b.encode(rec, fld, g))
                        self.b.code_slots = kept
                    if w != g:
                        where = f"[{s}]" if isinstance(want, list) else ""
                        bad.append(f"{rec}.{fld}{where} simh {self.word(rec, fld, w)} runs {self.word(rec, fld, g)}")
        return bad

    def word(self, rec: str, fld: str, v) -> str:
        if v is runs.UNKNOWN:
            return "unknown"
        if isinstance(v, CodeWord):
            return f"{v.word:06o}"
        if isinstance(v, runs.Member) and v.enum == "light":
            return v.name
        return f"{self.b.encode(rec, fld, v):06o}"

    def give(self, m: runs.Machine, state: dict, test_word: int):
        for rec, recs in state.items():
            m.state[rec] = copy.deepcopy(recs)
        m.state["console"]["test_word"] = runs.W(test_word)
        m.state["console"]["control_boxes"] = runs.W(0)    # headless SIMH: no buttons pressed
        m.state["scoreboard"] = []


class Simh:
    """One SIMH session, a command at a time."""

    def __init__(self, game: Game, setup: list[str]):
        self.game = game
        self.machine = frames.Machine(pdp1.ORACLE, setup)

    def command(self, text: str) -> str:
        self.machine.send(text)
        return self.machine.read()

    def snapshot(self) -> dict:
        values = {}
        for line in self.command(self.game.snapshot_command()).splitlines():
            if m := EXAMINED.match(line.strip()):
                key = m.group(1)
                values[int(key, 8) if key.isdigit() else key] = int(m.group(2), 8)
        return values

    def run(self, command: str) -> tuple[str, int]:
        """("break" or "halt", pc) of the stop that ends a go or cont."""
        reply = self.command(command)
        if m := BREAK.search(reply):
            return "break", int(m.group(1), 8)
        if m := HALT.search(reply):
            return "halt", int(m.group(1), 8) - 1
        raise RuntimeError(f"no stop: {reply[-500:]}")


# ------------------------------------------------------------ seeded cases

def a_case(game: Game, rng: random.Random, start: int | None) -> dict:
    """Records, test words and power-on words for one case. start: None for
    a frame from ml0, else the start address."""
    m = game.machine()
    st = {r: copy.deepcopy(m.state[r]) for r in RECORDS}
    o, sh = st["objects"], st["ships"]
    word = lambda: runs.W(rng.randrange(1 << 18))
    for s in range(0o30):
        o["routine"][s] = member("calc_routine", rng.choice(["none", "torpedo", "explosion"]))
        for f in ("x", "y", "counter", "cycles", "dx", "dy"):
            o[f][s] = word()
    o["routine"][0] = member("calc_routine", rng.choice(["first_spaceship"] * 4 + ["explosion", "in_hyperspace",
                                                                                   "breakout", "none"]))
    o["routine"][1] = member("calc_routine", rng.choice(["second_spaceship"] * 4 + ["explosion", "in_hyperspace",
                                                                                    "breakout", "none"]))
    for s in range(2):
        for f in sh:
            sh[f][s] = word()
        sh["saved_routine"][s] = member("calc_routine", ("first_spaceship", "second_spaceship")[s])
        sh["torpedoes"][s] = runs.W(rng.choice([NEG(1), NEG(2), 0, runs.MASK, 1, NEG(0o41), word().v]))
    st["random"]["number"] = word()
    st["frame"]["restart_delay"] = runs.W(rng.choice([NEG(1), NEG(1), NEG(2), runs.MASK, 0, NEG(0o100),
                                                      word().v]))
    st["frame"]["objects_seen"] = word()
    st["pacing"]["spare_time"] = word()
    st["outline_setting"]["separate_outlines"] = runs.W(rng.choice([runs.MASK, 0, word().v]))
    first = rng.choice([0, 1, 2, 7, rng.randrange(1 << 18)])
    st["score"] = {"first": runs.W(first),
                   "second": runs.W(first if rng.random() < 0.4 else rng.choice([0, 1, 3, rng.randrange(1 << 18)])),
                   "games_left": runs.W(rng.choice([0, NEG(1), NEG(1), NEG(2), NEG(5), 3, runs.MASK,
                                                    rng.randrange(1 << 18)]))}
    st["controls"]["source"] = member("control_source", rng.choice(["test_word", "control_boxes"]))
    lights = {"first_survived": member("light", rng.choice(["off", "on"])),
              "second_survived": member("light", rng.choice(["off", "on"]))}
    switches = lambda: rng.randrange(1 << 18) & ~0o40 | rng.choice([0, 0o40])
    case = {"state": st, "lights": lights, "start": start, "test_words": (switches(), switches())}
    if start is not None:                       # power-on: only the inputs come from core
        fresh = {r: copy.deepcopy(m.state[r]) for r in RECORDS}
        for r in ("objects", "ships"):          # the table is not on the tape: garbage the game clears
            fresh[r] = st[r]
        fresh["score"] = st["score"]
        fresh["outline_setting"]["separate_outlines"] = st["outline_setting"]["separate_outlines"]
        case["state"], case["lights"] = fresh, None
    return case


def run_cases(cases: list[dict], game: Game) -> tuple[int, dict]:
    sim = Simh(game, [f"break {game.sym['ml1']:o}", f"break {game.next_game:o}", f"break {game.halt:o}"])
    differ, seen = 0, {"object loop": 0, "new game": 0, "halts": 0, "power-on": 0}
    try:
        for k, case in enumerate(cases):
            st, tw = case["state"], case["test_words"]
            deposits = game.b.deposits({r: v for r, v in st.items() if r != "controls" or case["start"] is None},
                                       [r for r in RECORDS if r != "controls" or case["start"] is None])
            for a, v in deposits.items():
                sim.command(f"dep {a:o} {v:o}")
            lights = case["lights"]
            sim.command(f"dep PF {game.b.flags_word({'lights': lights}) if lights else 0:o}")
            sim.command(f"dep TW {tw[0]:o}")
            where = case["start"] if case["start"] is not None else game.sym["ml0"]
            stop, halts = sim.run(f"go {where:o}"), []
            while stop[1] == game.halt:
                values = sim.snapshot()
                halts.append((values["AC"], values["IO"], values))
                sim.command(f"dep TW {tw[1]:o}")
                sim.command(f"dep PC {game.halt + 1:o}")
                stop = sim.run("cont")
            want = game.decode(sim.snapshot())

            m = game.machine()
            game.give(m, st, tw[0])
            if lights:
                m.state["lights"] = copy.deepcopy(lights)
            m.stop_before = {"object_loop"}
            waits = []

            def at_wait(machine):
                waits.append(list(machine.state["scoreboard"]))
                machine.state["console"]["test_word"] = runs.W(tw[1])
            m.on_wait = at_wait
            name = {None: "frame", **pdp1.START}[case["start"]]
            ended = "new game"
            try:
                m.run(name)
            except runs.StopAt:
                ended = "object loop"
            bad = game.differences(m, want)
            if (ended == "object loop") != (stop[1] == game.sym["ml1"]):
                bad.append(f"runs reached the {ended}, simh stopped at {stop[1]:05o}")
            simh_shown = [(runs.W(ac), runs.W(io)) for ac, io, _ in halts]
            runs_shown = [w[-1] if w else None for w in waits]
            if simh_shown != runs_shown:
                bad.append(f"scores shown: simh {simh_shown}, runs {runs_shown}")
            seen[ended] += 1
            seen["halts"] += len(halts)
            seen["power-on"] += case["start"] is not None
            if bad:
                differ += 1
                if differ <= 5:
                    print(f"  case {k} ({name}): " + "; ".join(bad)[:700])
    finally:
        sim.machine.close()
    return differ, seen


# ---------------------------------------------------- the control word

def control_words(game: Game, rng: random.Random, n: int) -> int:
    """The control word Network from each source against SIMH entering its
    getter (mg2, or cwr at 040) with jsp: the IO it returns, with IO and the
    test word random on entry. Headless SIMH has no control boxes: iot 11
    leaves IO as it was, so a getter that did not clear IO first would
    return it."""
    differ = 0
    for source, entry in (("test_word", "mg2"), ("control_boxes", "cwr")):
        calls = [Inputs(rng.randrange(1 << 18), rng.randrange(1 << 18), test_word=rng.randrange(1 << 18))
                 for _ in range(n)]
        want = simh.run_jda(pdp1.SIMH, pdp1.ORACLE, game.sym[entry], calls, op="jsp")
        for c, w in zip(calls, want):
            m = game.machine()
            m.state["controls"]["source"] = member("control_source", source)
            m.state["console"]["test_word"] = runs.W(c.test_word)
            m.state["console"]["control_boxes"] = runs.W(0)
            m.run("control_word")
            if m.state["handoff"]["control_word"] != runs.W(w.io):
                differ += 1
                if differ <= 5:
                    print(f"  control word from {source}: simh {w.io:06o} runs {m.state['handoff']['control_word']}")
    print(f"control word: {2 * n} calls, {2 * n - differ} match, {differ} differ")
    return differ


# --------------------------------------------------------- scripted matches

def play(scenario, stops: int) -> tuple[str, int, dict, list[str]]:
    """One scripted match in SIMH, then the evaluator over every stop."""
    game = Game(scenario.deposits)
    sym = game.sym
    seam = sym["ml0"]
    setup = [f"dep SS {scenario.sense:o}", f"dep {sym['ran']:o} {scenario.seed:o}",
             *(f"dep {sym[name]:o} {value:o}" for name, value in scenario.deposits),
             f"break {seam:o}", f"break {sym['a']:o}"]
    sim = Simh(game, setup)
    controls = frames.Controls(scenario.policy, scenario.seed)
    power_on = game.decode(sim.snapshot())
    record = []                     # (kind, pc, state, AC, IO, test word after, game ended before it)
    try:
        tw = controls.next(frames.Stop("frame", seam))
        sim.command(f"dep TW {tw:o}")
        first_tw, command = tw, f"go {scenario.start:o}"
        while len(record) < stops:
            ended = False
            stop = sim.run(command)
            while stop == ("break", sym["a"]):
                ended = True
                stop = sim.run("cont")
            values = sim.snapshot()
            kind = "frame" if stop == ("break", seam) else "halt"
            tw = controls.next(frames.Stop(kind, stop[1]))
            record.append((kind, stop[1], game.decode(values), values["AC"], values["IO"], tw, ended))
            sim.command(f"dep TW {tw:o}")
            command = "cont"
    finally:
        sim.machine.close()

    counts = {"frames": 0, "games ended": 0, "halts shown": 0}
    bad: list[str] = []

    def fire(name: str, state: dict, test_word: int, k: int) -> tuple[int, list[str]]:
        """Fires name from state; returns the stop it should match next."""
        m = game.machine()
        game.give(m, state, test_word)
        m.stop_before = {"object_loop"}
        at = [k]
        trouble: list[str] = []

        def at_wait(machine):
            at[0] += 1
            if at[0] >= len(record):
                raise runs.StopAt("end of record")
            kind, pc, st, ac, io, tw, _ = record[at[0]]
            if kind != "halt" or pc != game.halt:
                trouble.append(f"stop {at[0]}: runs waits, simh {kind} at {pc:05o}")
                raise runs.StopAt("wait")
            counts["halts shown"] += 1
            if machine.state["scoreboard"][-1:] != [(runs.W(ac), runs.W(io))]:
                trouble.append(f"stop {at[0]}: shown {machine.state['scoreboard'][-1:]} simh {ac:06o} {io:06o}")
            machine.state["console"]["test_word"] = runs.W(tw)
        m.on_wait = at_wait
        try:
            m.run(name)
        except runs.StopAt as stop:
            if stop.name != "object_loop" or trouble:
                return -1, trouble
            nxt = at[0] + 1
            if nxt < len(record):
                if record[nxt][6]:
                    trouble.append(f"stop {nxt}: simh ended the game, runs did not")
                trouble += [f"stop {nxt}: {d}" for d in
                            game.differences(m, record[nxt][2], ["frame.restart_delay"])]
            return nxt, trouble
        counts["games ended"] += name == "frame"
        nxt = at[0] + 1
        if nxt < len(record):
            kind, pc = record[nxt][:2]
            if kind != "frame":
                trouble.append(f"stop {nxt}: runs began a frame, simh {kind} at {pc:05o}")
            elif name == "frame" and not record[k + 1][6]:
                trouble.append(f"stop {k + 1}: runs ended the game, simh did not")
            else:
                trouble += [f"stop {nxt}: {d}" for d in game.differences(m, record[nxt][2])]
        return nxt, trouble

    start = pdp1.START[scenario.start]
    k, trouble = fire(start, power_on, first_tw, -1)
    bad += trouble
    for k, (kind, pc, state, ac, io, tw, _) in enumerate(record):
        if kind != "frame":
            continue
        counts["frames"] += 1
        _, trouble = fire("frame", state, tw, k)
        bad += trouble
    return scenario.name, len(record), counts, bad


def main() -> int:
    cases = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    stops = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
    game = Game()
    status = 0
    if cases:
        rng = random.Random(1962)
        status |= bool(control_words(game, rng, min(cases, 1000)))
        starts = [rng.choice([None, None, None, *sorted(pdp1.START)]) for _ in range(cases)]
        batch = [a_case(game, rng, s) for s in starts]
        differ, seen = run_cases(batch, game)
        print(f"game control: {cases} cases, {cases - differ} match, {differ} differ; {seen}")
        status |= bool(differ)
    if stops:
        with ProcessPoolExecutor(min(len(frames.SCENARIOS), os.cpu_count() or 1)) as pool:
            results = list(pool.map(play, frames.SCENARIOS, [stops] * len(frames.SCENARIOS)))
        total = {"frames": 0, "games ended": 0, "halts shown": 0}
        failing = 0
        for name, n, counts, bad in results:
            for key in total:
                total[key] += counts[key]
            if bad:
                failing += 1
                print(f"  {name}: {len(bad)} differ; first: {bad[0][:300]}")
        print(f"scripted matches: {len(results)} played, {sum(r[1] for r in results)} stops, "
              f"{failing} with differences; {total}")
        status |= bool(failing)
    return status


if __name__ == "__main__":
    sys.exit(main())
