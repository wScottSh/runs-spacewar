"""lift.toml -> one Macro program -> macro1 -> sha256.

The program is every lifted C file compiled in the order lift.toml lists
them, as one unit of a program: a C name of external linkage is one Macro
symbol in every file (dialect.external_symbols). No source text takes part.

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

from . import dialect, emit, front, ir, layout
from .rules import RULES

LISTING_WORD = re.compile(r"^\s*\d*\s+([0-7]{5}) ([0-7]{6})(?:\s+(.*))?$")
LISTING_VARS = re.compile(r"^\s*\d+\s+([0-7]{5})\s+variables\b")
LISTING_SYMBOL = re.compile(r"^ (\w+)\s+([0-7]{6})$", re.M)
LISTING_LINE = re.compile(r"^ {0,4}\d+ ")
OUTPUT = Path("build/lift/program")     # .mac, .rim and .lst, under the root of lift.toml


@dataclass(frozen=True)
class LiftedFile:
    c: Path
    prefix: str         # the prefix of the file's generated labels


@dataclass(frozen=True)
class Compiled:
    file: LiftedFile
    unit: ir.Unit
    words: list[ir.Emitted]


def load(toml_path: Path) -> tuple[dict, list[LiftedFile]]:
    cfg = tomllib.loads(toml_path.read_text())
    files = [LiftedFile(toml_path.parent / u["c"], u["prefix"]) for u in cfg["unit"]]
    prefixes = [f.prefix for f in files]
    if bad := [p for p in prefixes if not dialect.GENERATED.fullmatch(p + "1")]:
        raise SystemExit(f"lift.toml: label prefixes are z and a letter: {bad}")
    if len(set(prefixes)) != len(prefixes):
        raise SystemExit("lift.toml: label prefixes must be unique per file")
    return cfg, files


def output(toml_path: Path, suffix: str) -> Path:
    return toml_path.parent / OUTPUT.with_suffix(suffix)


def compile_units(files: list[LiftedFile]) -> list[Compiled]:
    """Lower and lay out each file as a unit of one program."""
    asts = [front.parse(f.c) for f in files]
    linked = dialect.external_symbols(asts)
    units = [dialect.lower_unit(ast, f.prefix, linked) for ast, f in zip(asts, files)]
    if errors := disagreements(files, units):
        raise dialect.DialectError("\n".join(errors))
    if len(starts := [f.c.name for f, u in zip(files, units) if u.start]) > 1:
        raise dialect.DialectError(f"a program starts at one START function: {', '.join(starts)} each define one")
    return [Compiled(f, u, layout.place(u, f.prefix)) for f, u in zip(files, units)]


def units(toml_path: Path) -> dict[Path, ir.Unit]:
    """Each lifted file's unit, lowered as the build lowers it."""
    _, files = load(toml_path)
    return {c.file.c.resolve(): c.unit for c in compile_units(files)}


def _shape(sig: ir.Signature) -> tuple:
    return sig.conv, tuple((p.kind, p.pointer) for p in sig.params), sig.returns, sig.skips


def disagreements(files: list[LiftedFile], units: list[ir.Unit]) -> list[str]:
    """Every declaration of a function, and of an object that points to a
    function type, has one shape in every file of the program."""
    seen: dict[tuple[str, str], tuple[tuple, Path]] = {}
    errors = []
    for f, u in zip(files, units):
        named = [("function", n, s) for n, s in u.signatures.items()
                 if s.conv is not ir.Conv.INLINE and n not in u.statics]
        named += [("pointer", n, s) for n, s in (u.pointers or {}).items() if n not in u.statics]
        for kind, name, sig in named:
            first = seen.setdefault((kind, name), (_shape(sig), f.c))
            if first[0] != _shape(sig):
                errors.append(f"{f.c.name}: {name}: declared with another {kind} type than in "
                              f"{first[1].name}; declare it once, in a shared header")
    return errors


def listing(path: Path) -> tuple[dict[int, tuple[str, str]], int | None]:
    words: dict[int, tuple[str, str]] = {}
    variables = None
    for line in path.read_text(errors="replace").splitlines():
        if m := LISTING_VARS.match(line):
            variables = int(m.group(1), 8)
        elif m := LISTING_WORD.match(line):
            words.setdefault(int(m.group(1), 8), (m.group(2), m.group(3) or ""))
    return words, variables


def symbols(listing_text: str) -> dict[str, int]:
    return {s: int(v, 8) for s, v in LISTING_SYMBOL.findall(listing_text)}


def lifted_coverage(lst: Path) -> tuple[int, int]:
    """(words emitted by compiled C, all words placed) in an assembled listing.
    A compiled word's listing line carries its rule id. The words a line
    makes after its first, listed under it without a line number, belong to
    that line: the literal constants under a compiled CONSTANTS() count as
    compiled."""
    seen: set[int] = set()
    compiled = 0
    owner = ""
    for line in lst.read_text(errors="replace").splitlines():
        m = LISTING_WORD.match(line)
        if LISTING_LINE.match(line):
            owner = m.group(3) or "" if m else line
        if not m or int(m.group(1), 8) in seen:
            continue
        seen.add(int(m.group(1), 8))
        rule = re.search(r"/\s*([A-Z][A-Z0-9-]+)", owner)
        compiled += bool(rule and rule.group(1) in RULES)
    return compiled, len(seen)


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
                       f"rule {rule.group(1) if rule else '-'}")
            break
    else:
        out.append("every word is the oracle's: the tape differs in its start address or block order")
    return out


def build(toml_path: Path) -> int:
    toml_path = toml_path.resolve()
    cfg, files = load(toml_path)
    root = toml_path.parent
    macro1 = root / cfg["macro1"]
    if not macro1.exists():
        macro1.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["gcc", "-O2", "-w", "-o", str(macro1), str(root / cfg["macro1_src"])], check=True)
    from .cli import COMPILE_ERRORS
    try:
        compiled = compile_units(files)
    except COMPILE_ERRORS as e:
        print(f"error: {e}")
        return 1
    for c in compiled:
        print(f"  {c.file.c.relative_to(root)}  {sum(isinstance(w, ir.Word) for w in c.words)} lines")
    mac = output(toml_path, ".mac")
    mac.parent.mkdir(parents=True, exist_ok=True)
    mac.write_text(emit.program(f"pdp1cc {toml_path.name}", [c.words for c in compiled]))
    rim, lst = mac.with_suffix(".rim"), mac.with_suffix(".lst")
    for stale in (rim, lst):
        stale.unlink(missing_ok=True)
    asm = subprocess.run([str(macro1), "-r", "-d", mac.name], cwd=mac.parent, capture_output=True, text=True)
    if asm.returncode != 0 or not rim.exists() or "No errors detected" not in lst.read_text(errors="replace"):
        print(asm.stdout + asm.stderr + f"  macro1 reported errors: see {lst.relative_to(root)}")
        return 1
    got = hashlib.sha256(rim.read_bytes()).hexdigest()
    want = cfg["oracle_sha256"]
    done, total = lifted_coverage(lst)
    print(f"  lifted coverage: {done}/{total} words ({100 * done / total:.1f}%) from compiled C")
    if got == want:
        print(f"  rim {got}  MATCH")
        return 0
    print(f"  rim {got}  MISMATCH (want {want})")
    want_lst = root / cfg["oracle_listing"]
    if want_lst.exists():
        print("\n".join("  " + line for line in diagnose(lst, want_lst)))
    else:
        print(f"  ({want_lst} missing: run tools/oracle.sh for a word-level diagnosis)")
    return 1
