"""G1 reference checks: a native g++ build of lifted C against SIMH running
the same routine in the ORACLE binary (build/oracle.rim), call by call.
Shared by tools/check-*-reference.py.

Addresses come from the listing of the last `pdp1cc build`, which names
every lifted routine by the symbol the compiler gave it, pinned or
generated. That build matched the oracle, so its addresses are the
oracle's. Run `uv run pdp1cc build lift.toml` first."""
from __future__ import annotations

import hashlib
import random
from collections import Counter
from pathlib import Path

from pdp1cc import dialect, front, ir, splice
from pdp1cc.gate import corpus, reference, simh
from pdp1cc.gate.simh import Inputs

ROOT = Path(__file__).resolve().parent.parent
MINUS_ZERO = ir.WORD_MASK
MAX = 0o377777


def neg(v: int) -> int:
    return v ^ ir.WORD_MASK


def edges() -> list[int]:
    """0, -0, +-max, +-1 and every power of two with its negative."""
    pos = [0, 1, MAX] + [1 << k for k in range(1, 17)]
    return pos + [neg(v) for v in pos]


def seeded(seed: int, n: int) -> list[int]:
    rng = random.Random(seed)
    return [rng.randrange(1 << ir.WORD_BITS) for _ in range(n)]


def built_symbols() -> dict[str, int]:
    """The symbol table of the last build, which must match the oracle and be
    newer than every lifted file."""
    toml = ROOT / "lift.toml"
    cfg, regions = splice.load(toml)
    rim, lst = ROOT / "build/lift/spliced.rim", ROOT / "build/lift/spliced.lst"
    if not lst.exists() or hashlib.sha256(rim.read_bytes()).hexdigest() != cfg["oracle_sha256"]:
        raise SystemExit("build/lift does not hold a build matching the oracle: "
                         "run `uv run pdp1cc build lift.toml`")
    if any(f.stat().st_mtime > lst.stat().st_mtime for f in [toml, *(r.c for r in regions)]):
        raise SystemExit("build/lift is older than the lifted C: run `uv run pdp1cc build lift.toml`")
    return splice.symbols(lst.read_text(errors="replace"))


def lifted_units(c_files: list[Path]) -> dict[Path, ir.Unit]:
    """Each file lowered with its region's label prefix, as the build lowers it."""
    _, regions = splice.load(ROOT / "lift.toml")
    prefix = {r.c.resolve(): r.prefix for r in regions}
    return {f: dialect.lower_unit(front.parse(f), prefix[f.resolve()]) for f in c_files}


def check(label: str, lift_files: list[str], entry: str, calls: list[Inputs], domain: str) -> int:
    """Also compares, after every call, the entry word of each JDA function
    the lifted files define."""
    files = [ROOT / f for f in lift_files]
    sigs = {name: s for u in lifted_units(files).values() for name, s in u.signatures.items()}
    sig = sigs[entry]
    cells = [s for s in sigs.values() if reference.entry(s)]
    native = reference.build(files, ROOT / "build/ref" / entry, reference.call_expr(sig),
                             sig.inline_count, [reference.cell(s.name) for s in cells])
    address = built_symbols()
    want = simh.run_jda(ROOT / "build/pdp1", ROOT / "build/oracle.rim", address[sig.sym],
                        calls, bool(sig.inline_count), [address[s.sym] for s in cells],
                        op="xct" if sig.conv is ir.Conv.XCT else "jda")
    got = reference.run(native, calls)
    diffs = corpus.compare(calls, want, got, sig, [f"entry word of {s.name}" for s in cells])
    returns = Counter(o.returned_past for o in want)
    print(f"{label}: {len(calls)} calls ({domain}), {len(calls) - len(diffs)} match, "
          f"{len(diffs)} differ; oracle returned past call+1 by {dict(sorted(returns.items()))}")
    for d in diffs[:10]:
        print("  " + d)
    return 1 if diffs or len(got) != len(calls) else 0
