"""Run a JDA routine in SIMH pdp1 over many calls in one session.

The machine has no multiply/divide option, as Spacewar 3.1 assumes (SIMH
enables it by default, which turns `mus`/`dis` into full multiply/divide).

Each call: deposit AC, IO and by-name inputs, `go STUB`, examine AC, IO and
any watched addresses. The stub is

    lio IO_IN / lac AC_IN / jda entry / [lac BYNAME_IN] / hlt / hlt / hlt / hlt

so the halt address tells how many words past the call the routine returned:
its inline words plus any skip.

The simulator is built without a display: a `dpy` does nothing, and the I/O
synchronizer is set so that `ioh` never waits. To see what a routine plots,
a breakpoint on each display instruction examines AC and IO there and
continues; each call's points come back in order."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Scratch words above the star catalog (06077-07750), free in the oracle image.
AC_IN, IO_IN, BYNAME_IN = 0o7760, 0o7761, 0o7762
STUB = 0o7763
CALL = STUB + 2
HALTS = 4
HALT = re.compile(r"HALT instruction, PC: ([0-7]+)")
BREAK = re.compile(r"Breakpoint, PC: ([0-7]+)")
EXAMINE = re.compile(r"^(?:sim> )*(AC|IO|PF|[0-7]+):\s+([0-7]+)$")


class SimhError(Exception):
    pass


@dataclass(frozen=True)
class Inputs:
    ac: int
    io: int = 0
    byname: int = 0
    sense: int = 0              # sense switches 1..6 as bits 040..01


@dataclass(frozen=True)
class Outcome:
    ac: int
    io: int
    returned_past: int          # words past call+1 the routine returned to
    watched: tuple[int, ...] = ()
    plotted: tuple[tuple[int, int, int], ...] = ()     # (display instruction, x, y) in order


def run_jda(simh: Path, rim: Path, entry: int, calls: list[Inputs], byname: bool = False,
            watch: list[int | str] = (), timeout: int = 1800, op: str = "jda",
            inline: bool = False, deposits: dict[int, int] | None = None,
            display: dict[int, int] | None = None,
            each: list[dict[int, int]] | None = None) -> list[Outcome]:
    """op is the call instruction: jda, or xct for a one-word XCT routine.
    byname: the word after the call is `lac BYNAME_IN`. inline: it is the
    call's by-name input itself, a constant word (an INLINE parameter).
    watch holds addresses, or register names such as PF (the program flags).
    deposits are words set in core once, after loading: the routine's input data.
    display maps the address of each display instruction to its word: each
    one plotted is reported, in order, with AC and IO. each holds words
    set in core before each call, one dict per call."""
    words = [f"lio {IO_IN:o}", f"lac {AC_IN:o}", f"{op} {entry:o}"]
    if inline:
        words.append("0")
        byname = True
    elif byname:
        words.append(f"lac {BYNAME_IN:o}")
    words += ["hlt"] * HALTS
    script = ["set cpu nomdv", f"load {rim}", "dep IOS 1"]
    script += [f"break {a:o};ex AC;ex IO;continue" for a in sorted(display or {})]
    script += [f"dep {STUB + i:o} {w}" for i, w in enumerate(words)]
    script += [f"dep {a:o} {v:o}" for a, v in (deposits or {}).items()]
    for n, c in enumerate(calls):
        script += [f"dep {AC_IN:o} {c.ac:o}", f"dep {IO_IN:o} {c.io:o}", f"dep SS {c.sense:o}"]
        script += [f"dep {a:o} {v:o}" for a, v in (each[n] if each else {}).items()]
        if inline:
            script.append(f"dep {CALL + 1:o} {c.byname:o}")
        elif byname:
            script.append(f"dep {BYNAME_IN:o} {c.byname:o}")
        script += [f"go {STUB:o}", "ex AC", "ex IO"] + \
            [f"ex {a}" if isinstance(a, str) else f"ex {a:o}" for a in watch]
    script.append("quit")
    out = subprocess.run([str(simh)], input="\n".join(script) + "\n",
                         capture_output=True, text=True, timeout=timeout).stdout
    first_halt = CALL + 1 + int(byname)
    halts = [int(pc, 8) - 1 for pc in HALT.findall(out)]
    if len(halts) != len(calls) or any(not first_halt <= pc < STUB + len(words) for pc in halts):
        raise SimhError(f"expected {len(calls)} halts in the stub, got {[oct(h) for h in halts[:5]]}...\n"
                        f"{out[-2000:]}")
    values: list[int] = []
    plots: list[list[tuple[int, int, int]]] = [[] for _ in calls]
    call, at, point = -1, None, []
    for line in out.splitlines():
        if HALT.search(line):
            call += 1               # a call's examines follow its halt
        elif m := BREAK.search(line):
            at, point = int(m.group(1), 8), []
        elif m := EXAMINE.match(line):
            if at is not None:
                point.append(int(m.group(2), 8))
                if len(point) == 2:
                    plots[call + 1].append((display[at], *point))
                    at = None
            else:
                values.append(int(m.group(2), 8))
    per = 2 + len(watch)
    if len(values) != per * len(calls):
        raise SimhError(f"expected {per * len(calls)} examined values, got {len(values)}")
    return [Outcome(values[i * per], values[i * per + 1], pc - (CALL + 1),
                    tuple(values[i * per + 2:(i + 1) * per]), tuple(plots[i]))
            for i, pc in enumerate(halts)]
