"""G3: the compiler holds no memorized Spacewar output.

1. Lint tools/pdp1cc: no string literal equal to a symbol of the oracle's
   symbol table, and no 6-digit octal number equal to a word of the oracle.
2. Isolation: copy the compiler, lift/ and tests/corpus/ into an empty tree
   with no source/ and no build/oracle*, compile every C file there in a
   fresh environment, and require the output to equal the in-tree output.

Usage: uv run python tools/check-g3.py"""
import ast
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPILER = ROOT / "tools/pdp1cc"
OCTAL = re.compile(r"(?<![\w.])(?:0o|0)?([0-7]{6})(?![\w])")
C_STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"')


def oracle() -> tuple[set[str], set[str]]:
    lst = (ROOT / "build/oracle.lst").read_text(errors="replace")
    symbols = set(re.findall(r"^ (\w+)\s+[0-7]{6}$", lst, re.M))
    words = set(re.findall(r"^\s*\d*\s+[0-7]{5} ([0-7]{6})", lst, re.M))
    return symbols, words


def strings_in(path: Path) -> list[str]:
    text = path.read_text()
    if path.suffix == ".py":
        return [n.value for n in ast.walk(ast.parse(text))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return C_STRING.findall(text)


def lint() -> list[str]:
    symbols, words = oracle()
    problems = []
    files = [p for p in COMPILER.rglob("*") if p.suffix in {".py", ".h", ".cpp"}]
    for path in files:
        rel = path.relative_to(ROOT)
        for s in strings_in(path):
            if s in symbols:
                problems.append(f"{rel}: string literal {s!r} is a Spacewar symbol")
        for n, line in enumerate(path.read_text().splitlines(), 1):
            for m in OCTAL.finditer(line):
                if m.group(1) in words:
                    problems.append(f"{rel}:{n}: octal {m.group(0)} is a word of the oracle binary")
    print(f"lint: {len(files)} compiler files, {len(symbols)} oracle symbols, "
          f"{len(words)} distinct oracle words, {len(problems)} problems")
    return problems


def lower_all(tree: Path, files: list[Path]) -> dict[str, str]:
    out = {}
    for f in files:
        r = subprocess.run(["uv", "run", "--quiet", "--project", str(tree), "pdp1cc", "lower", str(f)],
                           cwd=tree, capture_output=True, text=True)
        out[str(f)] = r.stdout if r.returncode == 0 else "FAILED: " + r.stderr
    return out


def isolation() -> list[str]:
    files = [Path("lift/sqt.c")] + sorted(p.relative_to(ROOT) for p in (ROOT / "tests/corpus").glob("*.c"))
    want = lower_all(ROOT, files)
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp)
        for item in ["pyproject.toml", "uv.lock", "tools/pdp1cc", "lift", "tests/corpus"]:
            src, dst = ROOT / item, tree / item
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy(src, dst)
        assert not (tree / "source").exists() and not list(tree.glob("build/oracle*"))
        where = subprocess.run(["uv", "run", "--quiet", "--project", str(tree), "python", "-c",
                                "import pdp1cc; print(pdp1cc.__file__)"],
                               cwd=tree, capture_output=True, text=True).stdout.strip()
        if not where.startswith(str(tree)):
            return [f"isolated tree imported the compiler from {where!r}"]
        got = lower_all(tree, files)
    problems = [f"{f}: output differs without source/ and build/oracle*" for f in files
                if got[str(f)] != want[str(f)] or got[str(f)].startswith("FAILED")]
    print(f"isolation: {len(files)} files compiled in a tree without source/ or build/oracle*, "
          f"{len(files) - len(problems)} identical")
    return problems


def main() -> int:
    problems = lint() + isolation()
    for p in problems:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
