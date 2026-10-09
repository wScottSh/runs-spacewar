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

LABEL_DEF = re.compile(r"^([a-z0-9]+),", re.M)
LISTING_WORD = re.compile(r"^\s*\d*\s+([0-7]{5}) ([0-7]{6})(?:\s+(.*))?$")
LISTING_VARS = re.compile(r"^\s*\d+\s+([0-7]{5})\s+variables\b")


@dataclass(frozen=True)
class Region:
    name: str
    first: int
    last: int
    c: Path
    prefix: str


def load(toml_path: Path) -> tuple[dict, list[Region]]:
    cfg = tomllib.loads(toml_path.read_text())
    root = toml_path.parent
    regions = []
    for r in cfg["region"]:
        a, b = (int(x) for x in r["lines"].split("-"))
        regions.append(Region(r["name"], a, b, root / r["c"], r["prefix"]))
    prefixes = [r.prefix for r in regions]
    if len(set(prefixes)) != len(prefixes):
        raise SystemExit("lift.toml: label prefixes must be unique per region")
    return cfg, regions


def interface_errors(src_lines: list[str], region: Region, compiled: str) -> list[str]:
    """Symbols the original region defines and unlifted text uses must still be defined."""
    inside = "\n".join(src_lines[region.first - 1:region.last])
    outside = "\n".join(src_lines[:region.first - 1] + src_lines[region.last:])
    defined_now = set(LABEL_DEF.findall(compiled))
    errs = []
    for sym in LABEL_DEF.findall(inside):
        if re.search(rf"(?<![\w]){re.escape(sym)}(?![\w])", outside) and sym not in defined_now:
            errs.append(f"region {region.name} must define {sym} (used by unlifted text)")
    return errs


def listing(path: Path) -> tuple[dict[int, tuple[str, str]], int | None]:
    words: dict[int, tuple[str, str]] = {}
    variables = None
    for line in path.read_text(errors="replace").splitlines():
        if m := LISTING_VARS.match(line):
            variables = int(m.group(1), 8)
        elif m := LISTING_WORD.match(line):
            words.setdefault(int(m.group(1), 8), (m.group(2), m.group(3) or ""))
    return words, variables


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
    for r in sorted(regions, key=lambda r: r.first, reverse=True):
        text = compile_file(r.c, r.prefix)
        errors += interface_errors(src_lines, r, text)
        spliced[r.first - 1:r.last] = text.rstrip("\n").split("\n")
        print(f"  {r.name:<10} {r.first}-{r.last}  compiled from {r.c.relative_to(root)}")
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
