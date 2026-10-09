"""Run a JDA routine in SIMH pdp1 over many calls in one session.

The machine has no multiply/divide option, as Spacewar 3.1 assumes (SIMH
enables it by default, which turns `mus`/`dis` into full multiply/divide).

Each call: deposit AC, IO and by-name inputs, `go STUB`, examine AC, IO and
any watched addresses. The stub is

    lio IO_IN / lac AC_IN / jda entry / [lac BYNAME_IN] / hlt / hlt / hlt / hlt

so the halt address tells how many words past the call the routine returned:
its inline words plus any skip."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

AC_IN, IO_IN, BYNAME_IN = 0o7700, 0o7701, 0o7702
STUB = 0o7703
CALL = STUB + 2
HALTS = 4
HALT = re.compile(r"HALT instruction, PC: ([0-7]+)")
EXAMINE = re.compile(r"^(?:sim> )*(AC|IO|[0-7]+):\s+([0-7]+)$")


class SimhError(Exception):
    pass


@dataclass(frozen=True)
class Inputs:
    ac: int
    io: int = 0
    byname: int = 0


@dataclass(frozen=True)
class Outcome:
    ac: int
    io: int
    returned_past: int          # words past call+1 the routine returned to
    watched: tuple[int, ...] = ()


def run_jda(simh: Path, rim: Path, entry: int, calls: list[Inputs], byname: bool = False,
            watch: list[int] = (), timeout: int = 1800) -> list[Outcome]:
    words = [f"lio {IO_IN:o}", f"lac {AC_IN:o}", f"jda {entry:o}"]
    if byname:
        words.append(f"lac {BYNAME_IN:o}")
    words += ["hlt"] * HALTS
    script = ["set cpu nomdv", f"load {rim}"]
    script += [f"dep {STUB + i:o} {w}" for i, w in enumerate(words)]
    for c in calls:
        script += [f"dep {AC_IN:o} {c.ac:o}", f"dep {IO_IN:o} {c.io:o}"]
        if byname:
            script.append(f"dep {BYNAME_IN:o} {c.byname:o}")
        script += [f"go {STUB:o}", "ex AC", "ex IO"] + [f"ex {a:o}" for a in watch]
    script.append("quit")
    out = subprocess.run([str(simh)], input="\n".join(script) + "\n",
                         capture_output=True, text=True, timeout=timeout).stdout
    first_halt = CALL + 1 + int(byname)
    halts = [int(pc, 8) - 1 for pc in HALT.findall(out)]
    if len(halts) != len(calls) or any(not first_halt <= pc < STUB + len(words) for pc in halts):
        raise SimhError(f"expected {len(calls)} halts in the stub, got {[oct(h) for h in halts[:5]]}...\n"
                        f"{out[-2000:]}")
    values = [int(m.group(2), 8) for line in out.splitlines() if (m := EXAMINE.match(line))]
    per = 2 + len(watch)
    if len(values) != per * len(calls):
        raise SimhError(f"expected {per * len(calls)} examined values, got {len(values)}")
    return [Outcome(values[i * per], values[i * per + 1], pc - (CALL + 1),
                    tuple(values[i * per + 2:(i + 1) * per]))
            for i, pc in enumerate(halts)]
