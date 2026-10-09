"""G1 reference checks: a native g++ build of lifted C against SIMH running
the same routine in the ORACLE binary (build/oracle.rim), call by call.
Shared by tools/check-*-reference.py."""
from __future__ import annotations

import random
import re
from collections import Counter
from pathlib import Path

from pdp1cc import dialect, front, ir
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


def oracle_symbol(name: str) -> int:
    lst = (ROOT / "build/oracle.lst").read_text(errors="replace")
    return int(re.search(rf"^ {name}\s+([0-7]{{6}})$", lst, re.M).group(1), 8)


def signature(c_file: Path, name: str) -> ir.Signature:
    return dialect.lower_unit(front.parse(c_file)).signatures[name]


def check(label: str, lift_files: list[str], entry: str, calls: list[Inputs], domain: str) -> int:
    files = [ROOT / f for f in lift_files]
    sig = signature(files[-1], entry)
    native = reference.build(files, sig, ROOT / "build/ref" / entry)
    want = simh.run_jda(ROOT / "build/pdp1", ROOT / "build/oracle.rim", oracle_symbol(sig.sym),
                        calls, bool(sig.inline_count))
    got = reference.run(native, calls)
    diffs = corpus.compare(calls, want, got, sig, [])
    returns = Counter(o.returned_past for o in want)
    print(f"{label}: {len(calls)} calls ({domain}), {len(calls) - len(diffs)} match, "
          f"{len(diffs)} differ; oracle returned past call+1 by {dict(sorted(returns.items()))}")
    for d in diffs[:10]:
        print("  " + d)
    return 1 if diffs or len(got) != len(calls) else 0
