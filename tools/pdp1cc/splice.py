"""lift.toml regions -> spliced source -> macro1 -> sha256.

On a mismatch it reports first whether the `variables` base moved (a literal
count change shifts every pool variable), then the first differing address
with the rule id of the word emitted there."""
from __future__ import annotations

import hashlib
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .cli import compile_file
from .emit import BREAK
from .rules import RULES

LABEL_DEF = re.compile(r"^([a-z0-9]+),", re.M)
LISTING_WORD = re.compile(r"^\s*\d*\s+([0-7]{5}) ([0-7]{6})(?:\s+(.*))?$")
LISTING_VARS = re.compile(r"^\s*\d+\s+([0-7]{5})\s+variables\b")


@dataclass(frozen=True)
class Region:
    """A C file and the source line ranges its Macro text replaces, in order:
    REGION_BREAK() in the C ends the text for one range."""
    name: str
    ranges: tuple[tuple[int, int], ...]
    c: Path
    prefix: str

    def covers(self, n: int) -> bool:
        return any(a <= n <= b for a, b in self.ranges)


def load(toml_path: Path) -> tuple[dict, list[Region]]:
    cfg = tomllib.loads(toml_path.read_text())
    root = toml_path.parent
    regions = []
    for r in cfg["region"]:
        spans = [r["lines"]] if isinstance(r["lines"], str) else r["lines"]
        ranges = tuple(tuple(int(x) for x in span.split("-")) for span in spans)
        if list(ranges) != sorted(ranges):
            raise SystemExit(f"lift.toml: region {r['name']}: line ranges go in source order")
        regions.append(Region(r["name"], ranges, root / r["c"], r["prefix"]))
    spans = sorted(span for r in regions for span in r.ranges)
    if any(a[1] >= b[0] for a, b in zip(spans, spans[1:])):
        raise SystemExit("lift.toml: line ranges overlap")
    prefixes = [r.prefix for r in regions]
    if len(set(prefixes)) != len(prefixes):
        raise SystemExit("lift.toml: label prefixes must be unique per region")
    return cfg, regions


MACRO_COMMENT = re.compile(r"(^|\s)/.*")


def unlifted_text(toml_path: Path) -> str:
    """The source lines no region covers, with Macro comments removed. A `/`
    after whitespace starts a comment; `n/` sets the location."""
    cfg, regions = load(toml_path)
    lines = (toml_path.parent / cfg["source"]).read_text().split("\n")
    return "\n".join(MACRO_COMMENT.sub("", line) for n, line in enumerate(lines, 1)
                     if not any(r.covers(n) for r in regions))


def interface_errors(src_lines: list[str], region: Region, compiled: str) -> list[str]:
    """Symbols the original region defines and unlifted text uses must still be defined."""
    inside = "\n".join(line for n, line in enumerate(src_lines, 1) if region.covers(n))
    outside = "\n".join(line for n, line in enumerate(src_lines, 1) if not region.covers(n))
    defined_now = set(LABEL_DEF.findall(compiled))
    errs = []
    for sym in LABEL_DEF.findall(inside):
        if re.search(rf"(?<![\w]){re.escape(sym)}(?![\w])", outside) and sym not in defined_now:
            errs.append(f"region {region.name} must define {sym} (used by unlifted text)")
    return errs


def chunk_lines(text: str) -> list[list[str]]:
    """The Macro text for each line range of a region."""
    parts: list[list[str]] = [[]]
    for line in text.rstrip("\n").split("\n"):
        if line == BREAK:
            parts.append([])
        else:
            parts[-1].append(line)
    return parts


def listing(path: Path) -> tuple[dict[int, tuple[str, str]], int | None]:
    words: dict[int, tuple[str, str]] = {}
    variables = None
    for line in path.read_text(errors="replace").splitlines():
        if m := LISTING_VARS.match(line):
            variables = int(m.group(1), 8)
        elif m := LISTING_WORD.match(line):
            words.setdefault(int(m.group(1), 8), (m.group(2), m.group(3) or ""))
    return words, variables


def lifted_coverage(lst: Path) -> tuple[int, int]:
    """(words emitted by compiled C, all words placed) in an assembled listing.
    A compiled word's listing line carries its rule id; the constants pool
    is placed by unlifted text and counts as not lifted."""
    words, _ = listing(lst)
    compiled = sum(1 for _, text in words.values()
                   if (m := re.search(r"/\s*([A-Z][A-Z0-9-]+)", text)) and m.group(1) in RULES)
    return compiled, len(words)


def diagnose(got_lst: Path, want_lst: Path) -> list[str]:
    got, got_vars = listing(got_lst)
    want, want_vars = listing(want_lst)
    out = []
    if got_vars != want_vars:
        out.append(f"variables base MOVED: {want_vars:05o} -> {got_vars:05o} "
                   "(literal occurrence count changed)")
    else:
        out.append(f"variables base unchanged ({want_vars:05o})")
    for addr in sorted(set(got) | set(want)):
        g, w = got.get(addr), want.get(addr)
        if (g and g[0]) != (w and w[0]):
            rule = re.search(r"/\s*([A-Z][A-Z0-9-]+)", g[1]) if g else None
            out.append(f"first difference at {addr:05o}: want {w[0] if w else '-'} "
                       f"got {g[0] if g else '-'}  [{g[1].strip() if g else ''}]  "
                       f"rule {rule.group(1) if rule else '(unlifted text)'}")
            break
    return out


def build(toml_path: Path) -> int:
    toml_path = toml_path.resolve()
    cfg, regions = load(toml_path)
    root = toml_path.parent
    src_lines = (root / cfg["source"]).read_text().split("\n")
    work = root / "build" / "lift"
    work.mkdir(parents=True, exist_ok=True)
    macro1 = root / cfg["macro1"]
    if not macro1.exists():
        subprocess.run(["gcc", "-O2", "-w", "-o", str(macro1), str(root / cfg["macro1_src"])], check=True)

    spliced = list(src_lines)
    errors = []
    chunks: list[tuple[tuple[int, int], list[str]]] = []
    for r in regions:
        text = compile_file(r.c, r.prefix)
        errors += interface_errors(src_lines, r, text)
        parts = chunk_lines(text)
        if len(parts) != len(r.ranges):
            errors.append(f"region {r.name}: {len(r.ranges)} line ranges, but the C makes "
                          f"{len(parts)} (REGION_BREAK() separates them)")
            continue
        chunks += zip(r.ranges, parts)
        spans = ", ".join(f"{a}-{b}" for a, b in r.ranges)
        print(f"  {r.name:<10} {spans}  compiled from {r.c.relative_to(root)}")
    for (a, b), lines in sorted(chunks, reverse=True):
        spliced[a - 1:b] = lines
    if errors:
        print("\n".join(errors))
        return 1

    mac = work / "spliced.mac"
    mac.write_text("\n".join(spliced))
    for stale in (work / "spliced.rim", work / "spliced.lst"):
        stale.unlink(missing_ok=True)
    asm = subprocess.run([str(macro1), "-r", "-d", mac.name], cwd=work,
                         capture_output=True, text=True)
    if asm.returncode != 0 or not (work / "spliced.rim").exists():
        print(asm.stdout + asm.stderr)
        return 1
    got = hashlib.sha256((work / "spliced.rim").read_bytes()).hexdigest()
    want = cfg["oracle_sha256"]
    compiled, total = lifted_coverage(work / "spliced.lst")
    print(f"  lifted coverage: {compiled}/{total} words ({100 * compiled / total:.1f}%) from compiled C")
    if got == want:
        print(f"  rim {got}  MATCH")
        return 0
    print(f"  rim {got}  MISMATCH (want {want})")
    want_lst = root / cfg["oracle_listing"]
    if want_lst.exists():
        print("\n".join("  " + line for line in diagnose(work / "spliced.lst", want_lst)))
    else:
        print(f"  ({want_lst} missing: run tools/oracle.sh for a word-level diagnosis)")
    return 1
