"""Run a JDA routine in SIMH pdp1 over many inputs in one session.

A stub at STUB loads the input from IN, calls the routine with `jda`, and
halts. Each call: deposit the input, `go STUB`, examine AC (and any extra
addresses). Every call must halt at the stub's `hlt`."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

IN, STUB = 0o7700, 0o7701
HALT_PC = STUB + 3     # SIMH reports PC after the fetch of the stub's hlt
HALT = re.compile(r"HALT instruction, PC: ([0-7]+)")
EXAMINE = re.compile(r"^(?:sim> )*(AC|[0-7]+):\s+([0-7]+)$")


class SimhError(Exception):
    pass


def run_jda(simh: Path, rim: Path, entry: int, inputs: list[int],
            watch: list[int] = (), timeout: int = 600) -> list[tuple[int, ...]]:
    """For each input, the tuple (AC, *watched words) after the call."""
    script = [f"load {rim}",
              f"dep {IN + 1:o} lac {IN:o}",
              f"dep {IN + 2:o} jda {entry:o}",
              f"dep {IN + 3:o} hlt"]
    for v in inputs:
        script += [f"dep {IN:o} {v:o}", f"go {STUB:o}", "ex AC"]
        script += [f"ex {a:o}" for a in watch]
    script.append("quit")
    out = subprocess.run([str(simh)], input="\n".join(script) + "\n",
                         capture_output=True, text=True, timeout=timeout).stdout
    halts = [int(pc, 8) for pc in HALT.findall(out)]
    if len(halts) != len(inputs) or any(pc != HALT_PC for pc in halts):
        raise SimhError(f"expected {len(inputs)} halts at the stub, got {halts[:5]}...\n{out[-2000:]}")
    values = [int(m.group(2), 8) for line in out.splitlines() if (m := EXAMINE.match(line))]
    per = 1 + len(watch)
    if len(values) != per * len(inputs):
        raise SimhError(f"expected {per * len(inputs)} examined values, got {len(values)}")
    return [tuple(values[i:i + per]) for i in range(0, len(values), per)]
