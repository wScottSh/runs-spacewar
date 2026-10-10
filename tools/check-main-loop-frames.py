"""Frame-level reference check of the whole game: SIMH running the ORACLE
image against SIMH running the SPLICED image (the one `pdp1cc build` makes
from the lifted C), in lockstep, for many frames of scripted matches.

What it proves, and what it does not:

- Same image means same behaviour, so when the build matches the oracle
  hash the comparison is trivially clean. Its value is the coverage: it
  proves the scripted inputs execute the reported share of the lifted
  code words, and that both images behave identically under those inputs,
  stop by stop. It says nothing about what the C means natively; the
  native reference checks (tools/check-*-reference.py) cover that for the
  pure routines.
- When the build does not match, the first differing stop shows where the
  spliced image goes wrong under play.

Each scenario pins the start address (5: the test word is the control
word; 4: the control boxes, which headless SIMH reads as 0), the sense
switches, the seed in `ran`, optional deposits into the constants table
(`ddd`, torpedo tunables) and a seeded control policy. Each stop of the
machine is a frame (breakpoint at `ml0`) or a HALT (the score display at
a4, or the full object table). At every stop both machines get the same
next test word, chosen from the stop kind and the policy, and their
object table, scores, game count, restart delay, spare-time counter,
random number, AC, IO and program flags are compared. Every address comes
from the oracle's listing.

Coverage is taken on the spliced machine only. SIMH breakpoints see
fetches by PC, not words run by xct, so:
- each lifted code word gets a breakpoint that removes itself on its first
  hit;
- an xct whose operand nothing in the image stores into runs a fixed
  word: its hit counts that word (and the chain, if that word is an xct)
  as executed;
- an xct whose operand is stored into at run time (a by-name cell, a homed
  `xct .`), or an xct of such a cell, keeps a breakpoint that examines the
  cell, so its target is read at run time.
Data words get self-removing breakpoints for the first DATA_STOPS stops of
each scenario only (each live breakpoint slows every hit; SIMH's cost per
hit grows with the number of breakpoints). Not tracked: xct in code
generated at run time (the compiled outlines hold none) and indirect xct
(reported if one runs).

A lifted word is data if its listing line's first rule places data (an
initialized word, a JDA entry word that holds the argument, an entry
cell, reserved space, a pool variable) or it is a literal listed under a
compiled line, and no run executed it. Every other lifted word is code.

The build runs in a private copy of lift.toml, lift/ and the source, so a
concurrent rebuild of build/lift does not disturb the check.

Usage: uv run python tools/check-main-loop-frames.py [--frames N] [--jobs N]"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pdp1cc import splice
from pdp1cc.cli import compile_regions
from pdp1cc.rules import RULES

ROOT = Path(__file__).resolve().parent.parent
SIMH = ROOT / "build/pdp1"
ORACLE_RIM = ROOT / "build/oracle.rim"

LISTING_LINE = re.compile(r"^\s*(\d*)\s+([0-7]{5}) ([0-7]{6})(?:\s+(.*))?$")
NUMBERED = re.compile(r"^ {0,4}(\d+) (.*)$")
RULE_TAG = re.compile(r"/\s*([A-Z][A-Z0-9-]+)")
LABEL = re.compile(r"^((?:\w+,\s*)+)")
DATA_RULES = {"ST-PLACED", "JDA-ENTRY", "ST-ENTRY-CELL", "ST-RESERVE", "ST-POOL", "JDA-INLINE-ARG", "LAY-POOL"}
BREAK = re.compile(r"^Breakpoint, PC: ([0-7]+)")
HALT = re.compile(r"^HALT instruction, PC: ([0-7]+)")
EXAMINED = re.compile(r"^([0-7]+):\s+([0-7]+)$")

OP, INDIRECT, ADDR = 0o760000, 0o010000, 0o7777
XCT = 0o100000
JMP = 0o600000
STORES = {0o240000, 0o260000, 0o300000, 0o320000, 0o340000, 0o440000, 0o460000, 0o170000}
DATA_STOPS = 3

NOB = 0o30
PROPERTIES = [("mtb", NOB), ("nx1", NOB), ("ny1", NOB), ("na1", NOB), ("nb1", NOB), ("ndx", NOB),
              ("ndy", NOB), ("nom", 2), ("nth", 2), ("nfu", 2), ("ntr", 2), ("not", 2), ("nco", 2),
              ("nh1", 2), ("nh2", 2), ("nh3", 2), ("nh4", 2)]
TABLE_WORDS = sum(n for _, n in PROPERTIES)
WATCHED = ["1sc", "2sc", "gct", "ntd", "mtc", "ran"]

CCW, CW, THRUST, FIRE = 0o10, 0o4, 0o2, 0o1      # one ship's nibble, as ship 2 reads it
SHIP1_SHIFT = 14                                   # ship 1's nibble is the test word's high 4 bits
SHOW_SCORES = 0o40                                 # halt at a4 to show the scores after each game
GAMES_SHIFT = 6                                    # games in a match, test word bits 6..11
REPEATED_HALTS = 3                                 # "no space for new objects" halts in a loop


@dataclass(frozen=True)
class Word:
    addr: int
    value: int
    text: str            # the listing line that made the word
    line: int            # its line number in the assembled source
    literal: bool        # listed under that line, without a number of its own


@dataclass(frozen=True)
class Lifted:
    word: Word
    rule: str
    region: str
    data: bool


@dataclass(frozen=True)
class Image:
    rim: Path
    symbols: dict[str, int]
    words: dict[int, Word]


@dataclass(frozen=True)
class Policy:
    """Each ship holds a control nibble, drawn from `moves` by weight, for
    1..hold frames. The game bits of the test word step through `play`,
    `period` frames each; at the k-th halt they are halts[k % len(halts)]."""
    moves: tuple[tuple[int, int], ...]
    hold: int
    play: tuple[int, ...]
    halts: tuple[int, ...]
    period: int = 1500


@dataclass(frozen=True)
class Scenario:
    name: str
    start: int
    sense: int
    seed: int
    policy: Policy
    deposits: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class Watch:
    """The coverage breakpoints of the spliced machine."""
    code: tuple[int, ...]                 # removed on first hit
    data: tuple[int, ...]                 # removed on first hit, or after DATA_STOPS stops
    probes: dict[int, int]                # kept: breakpoint -> the xct cell it examines
    implied: dict[int, tuple[int, ...]]   # a hit here runs these words by xct


def switches(*on: int) -> int:
    """Sense switches 1..6 as SIMH's SS bits 040..01."""
    return sum(0o100 >> n for n in on)


def games(n: int, show: bool) -> int:
    return n << GAMES_SHIFT | (SHOW_SCORES if show else 0)


DUEL = ((0, 2), (CCW, 2), (CW, 2), (THRUST, 3), (FIRE, 3), (FIRE | CCW, 2), (FIRE | CW, 2),
        (FIRE | THRUST, 2), (CCW | CW, 1))
HYPER = ((0, 2), (CCW | CW, 4), (THRUST, 2), (FIRE, 1), (CCW | CW | FIRE, 1), (CCW | CW | THRUST, 1))
THRUSTER = ((THRUST, 4), (THRUST | CCW, 2), (THRUST | CW, 2), (0, 1))
GUNNER = ((FIRE, 4), (FIRE | CCW, 1), (FIRE | CW, 1), (0, 1))
IDLE = ((0, 1),)

MATCHES = (games(3, False), games(2, True), games(0, False), games(1, True))
HALTS = (games(3, False), games(0, True), games(2, False), games(0, False))


def scenario(name, start, sense, seed, moves, hold, margin, deposits=()) -> Scenario:
    """margin: where the heavens' right margin (fpr, 10000 at load) starts.
    It moves one place every 32 frames, so a run sees one stretch of sky;
    the margins below reach the window's wrap at 0 and the catalog ends
    that a few thousand frames can reach."""
    return Scenario(name, start, sense, seed, Policy(moves, hold, MATCHES, HALTS),
                    (("fpr", margin), *deposits))


SCENARIOS = [
    scenario("duel", 5, 0, 0o1, DUEL, 30, 0o100),
    scenario("duel-short-holds", 5, 0, 0o2, DUEL, 6, 0o2000),
    scenario("hyperspace", 5, 0, 0o3, HYPER, 15, 0o3000),
    scenario("hyperspace-hammer-sw6", 5, switches(6), 0o21, ((CCW | CW, 1), (0, 1)), 2, 0o10000,
             (("mhs", 0o710001),)),
    scenario("thrust-sw1", 5, switches(1), 0o4, THRUSTER, 40, 0o6440),
    scenario("light-star-sw2", 5, switches(2), 0o5, DUEL, 25, 0o11240),
    scenario("one-shot-sw3", 5, switches(3), 0o6, GUNNER, 3, 0o2),
    scenario("no-heavens-sw4", 5, switches(4), 0o7, HYPER, 20, 0o10000),
    scenario("star-sw5", 5, switches(5), 0o10, THRUSTER, 30, 0o5000),
    scenario("no-star-sw6", 5, switches(6), 0o11, DUEL, 25, 0o17700),
    scenario("all-switches", 5, switches(1, 2, 3, 4, 5, 6), 0o12, DUEL, 20, 0o12000),
    scenario("outline-ddd-0", 5, 0, 0o13, DUEL, 20, 0o1000, (("ddd", 0),)),
    scenario("idle-sw5", 5, switches(5), 0o14, IDLE, 1, 0o14000),
    scenario("control-boxes", 4, 0, 0o15, IDLE, 1, 0o10000),
    scenario("control-boxes-sw5", 4, switches(5), 0o16, IDLE, 1, 0o4000),
    scenario("full-table", 5, 0, 0o17, GUNNER, 200, 0o10000, (("rlt", 0o710004),)),
    scenario("torpedoes-out", 5, 0, 0o20, GUNNER, 500, 0o16000, (("tlf", 0o710010),)),
]


def read_listing(path: Path) -> dict[int, Word]:
    """Each word with the numbered line that made it: a word listed without
    a line number (a literal of `constants`) belongs to the line above."""
    words: dict[int, Word] = {}
    line, owner = 0, ""
    for text in path.read_text(errors="replace").splitlines():
        m = LISTING_LINE.match(text)
        if n := NUMBERED.match(text):
            line, owner = int(n.group(1)), (m.group(4) or "").strip() if m else n.group(2)
        if m and int(m.group(2), 8) not in words:
            addr = int(m.group(2), 8)
            words[addr] = Word(addr, int(m.group(3), 8), owner, line, not m.group(1))
    return words


def image(rim: Path, lst: Path) -> Image:
    return Image(rim, splice.symbols(lst.read_text(errors="replace")), read_listing(lst))


def build(work: Path) -> tuple[Image, list[tuple[str, int, int]], str]:
    """Splices and assembles the current lift/ in a private copy. Returns the
    spliced image, each region chunk's line span in spliced.mac, and the
    build's verdict."""
    cfg, _ = splice.load(ROOT / "lift.toml")
    shutil.copy(ROOT / "lift.toml", work / "lift.toml")
    shutil.copytree(ROOT / "lift", work / "lift")
    for rel in (cfg["source"], cfg["macro1"]):
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, work / rel)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        status = splice.build(work / "lift.toml")
    out = work / "build/lift"
    if not (out / "spliced.lst").exists() or not (out / "spliced.rim").exists():
        raise SystemExit("pdp1cc build failed:\n" + log.getvalue())
    cfg, regions = splice.load(work / "lift.toml")
    dropped = splice.dropped(cfg)
    chunks = sorted([(span, r.name, len(part)) for r in regions
                     for span, part in zip(r.ranges, compile_regions(r.c, r.prefix))]
                    + [(span, "", 0) for span in dropped])
    spans, shift = [], 0
    for (a, b), name, n in chunks:
        if name:
            spans.append((name, a + shift, a + shift + n - 1))
        shift += n - (b - a + 1)
    sha = hashlib.sha256((out / "spliced.rim").read_bytes()).hexdigest()
    verdict = "MATCH" if status == 0 and sha == cfg["oracle_sha256"] else f"MISMATCH (rim {sha[:16]})"
    return image(out / "spliced.rim", out / "spliced.lst"), spans, verdict


def lifted_words(img: Image, spans: list[tuple[str, int, int]]) -> dict[int, Lifted]:
    out = {}
    for w in img.words.values():
        m = RULE_TAG.search(w.text)
        if not m or m.group(1) not in RULES:
            continue
        region = next((name for name, a, b in spans if a <= w.line <= b), "?")
        out[w.addr] = Lifted(w, m.group(1), region, w.literal or m.group(1) in DATA_RULES)
    return out


def plan(img: Image, lifted: dict[int, Lifted], seam: int) -> Watch:
    words = {a: w.value for a, w in img.words.items()}
    stored = {v & ADDR for v in words.values() if v & OP in STORES and not v & INDIRECT}
    xct = {a for a, v in words.items() if v & OP == XCT}
    moving = {a for a in xct if a in stored or words[a] & INDIRECT}
    probes, implied = {a: a for a in moving}, {}
    for a in sorted(xct - moving):
        chain, t = [], words[a] & ADDR
        while True:
            chain.append(t)
            if t in moving:
                probes[a] = t
                break
            if t not in xct or t in chain[:-1]:
                break
            t = words[t] & ADDR
        implied[a] = tuple(chain)
    code = {a for a, w in lifted.items() if not w.data}
    code |= {a for a, chain in implied.items() if set(chain) & set(lifted)}
    data = {a for a, w in lifted.items() if w.data}
    skip = set(probes) | {seam}
    return Watch(tuple(sorted(code - skip)), tuple(sorted(data - code - skip)), probes, implied)


class Machine:
    """One SIMH pdp1 driven over pipes, a command at a time."""

    def __init__(self, rim: Path, setup: list[str]):
        self.proc = subprocess.Popen([str(SIMH)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, bufsize=0)
        self.pending = b""
        self.read()
        for c in ["set cpu nomdv", f"load {rim}", "dep IOS 1", *setup]:
            self.send(c)
            if (reply := self.read()).strip():
                raise RuntimeError(f"simh: {c!r} -> {reply.strip()}")

    def send(self, command: str) -> None:
        self.proc.stdin.write(command.encode() + b"\n")

    def read(self) -> str:
        while b"sim> " not in self.pending:
            data = os.read(self.proc.stdout.fileno(), 1 << 16)
            if not data:
                raise RuntimeError("simh exited: " + self.pending.decode(errors="replace")[-2000:])
            self.pending += data
        reply, _, self.pending = self.pending.partition(b"sim> ")
        return reply.decode()

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait()


@dataclass(frozen=True)
class Stop:
    kind: str            # "frame" or "halt"
    pc: int


@dataclass
class Result:
    name: str
    stops: int = 0
    halts: int = 0
    difference: str = ""
    executed: set[int] = field(default_factory=set)
    notes: set[str] = field(default_factory=set)


def parse_run(reply: str, seam: int, watch: Watch | None = None, result: Result | None = None) -> Stop:
    """The stop that ended a `go` or `cont`, recording on the way each
    breakpoint hit and the words it ran by xct."""
    stop, hit = None, None
    for line in reply.splitlines():
        line = line.strip()
        if m := BREAK.match(line):
            hit = int(m.group(1), 8)
            if hit == seam:
                stop = Stop("frame", seam)
            if result is not None:
                result.executed.add(hit)
                result.executed.update(watch.implied.get(hit, ()))
        elif m := HALT.match(line):
            stop = Stop("halt", int(m.group(1), 8) - 1)
            if result is not None:
                result.executed.add(stop.pc)
        elif (m := EXAMINED.match(line)) and result is not None and hit in watch.probes:
            word = int(m.group(2), 8)
            if word & OP == XCT and word & INDIRECT:
                result.notes.add(f"indirect xct ran at {int(m.group(1), 8):05o}: its target is not counted")
            elif word & OP == XCT:
                result.executed.add(word & ADDR)
        elif line:
            raise RuntimeError(f"unexpected simh output: {line}\n{reply[-1500:]}")
    if stop is None:
        raise RuntimeError(f"no stop in simh output:\n{reply[-1500:]}")
    return stop


def snapshot_command(symbols: dict[str, int]) -> str:
    mtb = symbols["mtb"]
    names = ",".join(f"{symbols[n]:o}" for n in WATCHED)
    return f"ex {mtb:o}-{mtb + TABLE_WORDS - 1:o},{names},AC,IO,PF"


def snapshot_values(reply: str) -> list[str]:
    return [line.split(":", 1)[1].strip() for line in reply.splitlines() if ":" in line]


def describe(symbols: dict[str, int], index: int) -> str:
    if index < TABLE_WORDS:
        for name, n in PROPERTIES:
            if index < n:
                return f"{name}+{index:o} ({symbols[name] + index:05o})"
            index -= n
    return (WATCHED + ["AC", "IO", "PF"])[index - TABLE_WORDS]


class Controls:
    def __init__(self, policy: Policy, seed: int):
        self.policy = policy
        self.rng = random.Random(seed)
        self.held = [(0, 0), (0, 0)]
        self.frames = 0
        self.halts = 0

    def next(self, stop: Stop) -> int:
        p = self.policy
        if stop.kind == "halt":
            self.halts += 1
            return p.halts[(self.halts - 1) % len(p.halts)]
        nibbles = []
        for ship in range(2):
            move, left = self.held[ship]
            if left <= 0:
                moves, weights = zip(*p.moves)
                move = self.rng.choices(moves, weights)[0]
                left = self.rng.randint(1, p.hold)
            self.held[ship] = (move, left - 1)
            nibbles.append(move)
        self.frames += 1
        return nibbles[0] << SHIP1_SHIFT | nibbles[1] | p.play[self.frames // p.period % len(p.play)]


def run_scenario(scenario: Scenario, oracle: Image, spliced: Image, watch: Watch, stops: int) -> Result:
    result = Result(scenario.name)
    symbols = oracle.symbols
    seam = symbols["ml0"]
    common = [f"dep SS {scenario.sense:o}", f"dep {symbols['ran']:o} {scenario.seed:o}",
              *(f"dep {symbols[name]:o} {value:o}" for name, value in scenario.deposits),
              f"break {seam:o}"]
    coverage = [f"break {a:o};ex {cell:o};cont" for a, cell in watch.probes.items()]
    coverage += [f"break {a:o};nobreak {a:o};cont" for a in watch.code + watch.data]
    machines = [Machine(oracle.rim, common), Machine(spliced.rim, common + coverage)]
    controls = Controls(scenario.policy, scenario.seed)
    snapshot = snapshot_command(symbols)
    try:
        for m in machines:
            m.send(f"dep TW {controls.next(Stop('frame', seam)):o}")
            m.read()
            m.send(f"go {scenario.start:o}")
        repeats, last_halt = 0, None
        while result.stops < stops:
            want = parse_run(machines[0].read(), seam)
            got = parse_run(machines[1].read(), seam, watch, result)
            result.stops += 1
            for m in machines:
                m.send(snapshot)
            values = [snapshot_values(m.read()) for m in machines]
            if want != got or values[0] != values[1]:
                k = next((k for k, (a, b) in enumerate(zip(*values)) if a != b), None)
                where = (f"{describe(symbols, k)} oracle {values[0][k]} spliced {values[1][k]}"
                         if k is not None else f"oracle {want}, spliced {got}")
                result.difference = f"stop {result.stops}: {where}"
                break
            if got.kind == "frame":
                last_halt = None
            else:
                result.halts += 1
                repeats = repeats + 1 if got.pc == last_halt else 0
                last_halt = got.pc
                after = spliced.words.get(got.pc + 1)
                if repeats and after is not None and after.value == JMP | got.pc:
                    result.executed.add(got.pc + 1)     # `hlt / jmp .-1`: cont ran the jump back
                if repeats >= REPEATED_HALTS:
                    result.notes.add(f"{scenario.name}: halt at {got.pc:05o} repeats, scenario ended there")
                    break
            if result.stops == DATA_STOPS:
                for a in watch.data:
                    machines[1].send(f"nobreak {a:o}")
                    machines[1].read()
            tw = controls.next(got)
            for m in machines:
                m.send(f"dep TW {tw:o}")
                m.send("cont")
                m.read()
    finally:
        for m in machines:
            m.close()
    return result


def nearest_label(img: Image, addr: int) -> str:
    labels = [(a, m.group(1).split(",")[0]) for a, w in img.words.items()
              if not w.literal and (m := LABEL.match(w.text))]
    best = max(((a, name) for a, name in labels if a <= addr), default=None)
    if best is None:
        return f"{addr:05o}"
    return best[1] if best[0] == addr else f"{best[1]}+{addr - best[0]:o}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=6000, help="stops per scenario")
    parser.add_argument("--jobs", type=int, default=min(len(SCENARIOS), os.cpu_count() or 1))
    parser.add_argument("--unexecuted", type=int, default=40, help="unexecuted code words to list")
    args = parser.parse_args()
    began = time.time()
    cfg, _ = splice.load(ROOT / "lift.toml")
    oracle = image(ORACLE_RIM, ROOT / cfg["oracle_listing"])
    with tempfile.TemporaryDirectory(prefix="check-main-loop-") as tmp:
        spliced, spans, verdict = build(Path(tmp))
        lifted = lifted_words(spliced, spans)
        watch = plan(spliced, lifted, oracle.symbols["ml0"])
        n = len(SCENARIOS)
        with ProcessPoolExecutor(args.jobs) as pool:
            results = list(pool.map(run_scenario, SCENARIOS, [oracle] * n, [spliced] * n,
                                    [watch] * n, [args.frames] * n))

    executed = set().union(*(r.executed for r in results))
    notes = set().union(*(r.notes for r in results))
    code = {a: w for a, w in lifted.items() if not w.data or a in executed}
    data_ran = sorted(a for a, w in lifted.items() if w.data and a in executed)
    print(f"build: {verdict}; lifted words: {len(lifted)}, {len(code)} code "
          f"(incl. {len(data_ran)} data words that ran), {len(lifted) - len(code)} data")
    if data_ran:
        print("  data words that ran: " + ", ".join(f"{a:05o} {nearest_label(spliced, a)}" for a in data_ran))
    diffs = [r for r in results if r.difference]
    print(f"scenarios: {len(results)}; stops compared: {sum(r.stops for r in results)} "
          f"({sum(r.halts for r in results)} halts); differences: {len(diffs)}")
    for r in results:
        print(f"  {r.name:<20} {r.stops:>6} stops {r.halts:>4} halts"
              + (f"  DIFFERS at {r.difference}" if r.difference else ""))
    hit = sum(1 for a in code if a in executed)
    print(f"lifted code executed: {hit}/{len(code)} ({100 * hit / max(1, len(code)):.1f}%)")
    per = defaultdict(lambda: [0, 0])
    for a, w in code.items():
        per[w.region][0] += a in executed
        per[w.region][1] += 1
    for region, (h, t) in sorted(per.items()):
        print(f"  {region:<12} {h:>5}/{t:<5} ({100 * h / t:.1f}%)")
    missed = sorted(a for a in code if a not in executed)
    shown = "" if len(missed) <= args.unexecuted else f" (first {args.unexecuted})"
    print(f"unexecuted lifted code words: {len(missed)}{shown}")
    for a in missed[:args.unexecuted]:
        w = code[a]
        print(f"  {a:05o} {w.region:<10} {nearest_label(spliced, a):<10} {w.word.text}")
    for note in sorted(notes):
        print(f"note: {note}")
    print(f"runtime: {time.time() - began:.1f}s")
    return 1 if diffs or verdict != "MATCH" else 0


if __name__ == "__main__":
    sys.exit(main())
