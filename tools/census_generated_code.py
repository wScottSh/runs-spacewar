"""Code a PDP-1 program writes and then runs, as SIMH shows it.

Loads any PDP-1 tape (RIM or binary) into SIMH, runs it from the start
address the loader leaves, and follows core through CPU history. A word
counts as generated when an instruction writes it whole (dac, dio, dzm, or
the jda/cal store) at run time and the program later executes it, directly
or through xct. Words the tape's loader writes, from the top of core, are
loading. Address-field patches (dap, dip, idx, isp) are the cursor
and return idiom and are counted apart.

Reports each run of generated words: its span, how many times control
entered it, the instructions that wrote it, and how control left it.

Usage: census_generated_code.py TAPE [--steps N] [--chunks K] [--ss OCTAL] [--tw OCTAL] [--start OCTAL]
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import pdp1
import reach_oracle as ro

frames = ro.frames


class Booted(frames.Machine):
    """Reads the tape in as the machine does: attached to the reader and
    booted in read-in mode, so a tape's own loader reads the blocks after
    it. Stops at the first instruction below the loader's region, the
    program's start, before any history is kept."""

    def __init__(self, tape: Path, loader: int, setup: list[str]):
        self.proc = frames.subprocess.Popen([str(frames.SIMH)], stdin=frames.subprocess.PIPE,
                                            stdout=frames.subprocess.PIPE, stderr=frames.subprocess.STDOUT, bufsize=0)
        self.pending = b""
        self.read()
        self.punch = tempfile.NamedTemporaryFile(suffix=".ptp")
        for c in ["set cpu nomdv", f"attach -r ptr {tape}", f"attach ptp {self.punch.name}", f"break 0-{loader - 1:o}"]:
            self.send(c)
            self.read()
        self.send("boot ptr")
        self.boot = (self.read().strip().splitlines() or ["no stop"])[-1]
        for c in [f"nobreak 0-{loader - 1:o}", *setup]:
            self.send(c)
            if (reply := self.read()).strip():
                raise RuntimeError(f"simh: {c!r} -> {reply.strip()}")


def run(tape: Path, steps: int, chunks: int, ss: int, tw: int, start: int | None = None,
        loader: int = 0o7700) -> dict:
    setup = [f"dep SS {ss:o}", f"dep TW {tw:o}", "dep IOS 1", f"set cpu history={ro.HISTORY}",
             *([f"dep PC {start:o}"] if start is not None else [])]
    m = Booted(tape, loader, setup)
    try:
        m.send("ex PC")
        entry = int(m.read().split()[-1], 8)
        m.send("ex 0-7777")
        core = {int(a, 8): int(v, 8) for a, v in re.findall(r"^([0-7]+):\s+([0-7]+)", m.read(), re.M)}
        whole: dict[int, set[int]] = defaultdict(set)      # address -> pcs that wrote it whole
        patched: dict[int, set[int]] = defaultdict(set)
        executed: Counter = Counter()
        generated_runs: Counter = Counter()                # pc executed that was written whole
        entries: Counter = Counter()                       # (from, to) jumps into generated words
        exits: Counter = Counter()                         # (from, to) jumps out of them
        halted, halts = None, 0
        prev = None
        for _ in range(chunks):
            m.send(f"step {steps}")
            reply = m.read()
            m.send(f"show cpu history={ro.HISTORY}")
            hist = ro.parse_history(m.read())
            m.send("set cpu history=0"); m.read()
            m.send(f"set cpu history={ro.HISTORY}"); m.read()
            for i, s in enumerate(hist):
                pcs = [s.pc]
                op, ind, addr, ea = s.op, s.indirect, s.address, s.ea
                while op == "XCT":          # SIMH lists an xct once, with the executed word's effective address
                    t = core.get(addr, 0) & ro.ADDRESS if ind else addr
                    pcs.append(t)
                    w = core.get(t, 0)
                    op, ind, addr = ro.MNEMONIC.get(w >> 12 & 0o76, "?"), bool(w & 0o10000), w & ro.ADDRESS
                for pc in pcs:
                    executed[pc] += 1
                    if pc in whole:
                        generated_runs[pc] += 1
                        if prev is not None and prev not in whole and prev + 1 != pc:
                            entries[(prev, pc)] += 1
                    elif prev is not None and prev in whole and prev + 1 != pc:
                        exits[(prev, pc)] += 1
                    prev = pc
                if op in ("JDA", "CAL"):
                    t = 0o100 if op == "CAL" else (ea if ind and ea is not None else addr)
                    whole[t].add(s.pc); core[t] = s.ac
                    continue
                if ea is None or op not in ro.MEMORY or op in ro.JUMP:
                    continue
                if op in ro.WRITE_WHOLE:
                    if s.pc < loader:       # the loader's writes are loading, not code the program makes
                        whole[ea].add(s.pc)
                    else:
                        whole.pop(ea, None)
                    core[ea] = {"DAC": s.ac, "DIO": s.io, "DZM": 0}[op]
                elif op == "DAP":
                    patched[ea].add(s.pc); core[ea] = core.get(ea, 0) & ~ro.ADDRESS | s.ac & ro.ADDRESS
                elif op == "DIP":
                    patched[ea].add(s.pc); core[ea] = core.get(ea, 0) & ro.ADDRESS | s.ac & ~ro.ADDRESS & 0o777777
                elif op in ro.STEP:
                    patched[ea].add(s.pc)
                    if i + 1 < len(hist):
                        core[ea] = hist[i + 1].ac
            if "Step expired" not in reply:
                last = (reply.strip().splitlines() or ["stopped"])[-1]
                if "HALT instruction" in last and halts < 50:
                    halts += 1          # the operator sets the switches and presses continue
                    continue
                halted = last
                break
        m.send("ex 0-7777")
        actual = {int(a, 8): int(v, 8) for a, v in re.findall(r"^([0-7]+):\s+([0-7]+)", m.read(), re.M)}
    finally:
        m.close()
    drift = [a for a, v in actual.items() if core.get(a, 0) != v]
    return dict(halts=halts, boot=m.boot, entry=entry, whole=whole, patched=patched, executed=executed, generated=generated_runs,
                entries=entries, exits=exits, halted=halted, drift=drift,
                instructions=sum(executed.values()))


def spans(addresses) -> list[tuple[int, int]]:
    out = []
    for a in sorted(addresses):
        if out and a == out[-1][1] + 1:
            out[-1] = (out[-1][0], a)
        else:
            out.append((a, a))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tape", type=Path)
    ap.add_argument("--steps", type=int, default=60000)
    ap.add_argument("--chunks", type=int, default=20)
    ap.add_argument("--ss", type=lambda v: int(v, 8), default=0)
    ap.add_argument("--tw", type=lambda v: int(v, 8), default=0o252525)
    ap.add_argument("--start", type=lambda v: int(v, 8), default=None)
    a = ap.parse_args()
    r = run(a.tape, a.steps, a.chunks, a.ss, a.tw, a.start)
    gen = r["generated"]
    drift = "matches SIMH" if not r["drift"] else f"drifts at {len(r['drift'])} words"
    print(f"{a.tape.name}: read in ({r['boot']}), entered at {r['entry']:o}; {r['instructions']} instructions"
          + (f", continued past {r['halts']} halts" if r["halts"] else "")
          + (f", stopped: {r['halted']}" if r["halted"] else "")
          + f"; core model {drift}")
    print(f"  address-field patches (cursor/return idiom): {len(r['patched'])} words")
    if not gen:
        print("  generated code: none executed")
        return 0
    for lo, hi in spans(gen):
        words = range(lo, hi + 1)
        writers = sorted({w for x in words for w in r["whole"][x]})
        ins = sum(c for (f, t), c in r["entries"].items() if lo <= t <= hi)
        outs = Counter(t for (f, t), c in r["exits"].items() if lo <= f <= hi for _ in range(c))
        print(f"  generated {lo:05o}-{hi:05o}: {hi - lo + 1} words, {sum(gen[x] for x in words)} executions, "
              f"{ins} entries; written by {' '.join(f'{w:o}' for w in writers[:8])}"
              + (" ..." if len(writers) > 8 else "")
              + f"; leaves to {' '.join(f'{t:o}x{c}' for t, c in outs.most_common(4))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
