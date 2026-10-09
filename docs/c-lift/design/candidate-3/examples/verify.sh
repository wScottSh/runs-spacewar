#!/usr/bin/env bash
# Splice hand-lowered Macro (*.lower.mac) into a copy of the original source in
# place of the regions named in its first line ("/ region A-B[,C-D...]"),
# assemble with macro1, and check the oracle hash. Proves the hand traces, not
# the compiler (the compiler does not exist yet).
# Usage: verify.sh [file.lower.mac ...]   (default: all in this dir, together and singly)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
SRC="$ROOT/source/spacewar3.1_complete.txt"
SHA=8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf
M1="$ROOT/build/macro1"
[ -x "$M1" ] || gcc -O2 -w -o "$M1" "$ROOT/tools/macro1.c"
WORK="${TMPDIR:-/tmp}/c3verify.$$"; mkdir -p "$WORK"; trap 'rm -rf "$WORK"' EXIT

splice() {   # splice files... > out
  python3 -I - "$SRC" "$@" <<'PY'
import sys, re
src = open(sys.argv[1]).read().split('\n')
repl = []  # (start, end, lines) 1-based inclusive; a file may name several regions,
           # separated in the body by lines "/ --- region N" (N = index)
for f in sys.argv[2:]:
    body = open(f).read().split('\n')
    m = re.match(r'/ region ([0-9,\-]+)', body[0])
    ranges = [tuple(map(int, r.split('-'))) for r in m.group(1).split(',')]
    chunks, cur = [], []
    for ln in body[1:]:
        if ln.startswith('/ --- region'):
            chunks.append(cur); cur = []
        else:
            cur.append(ln)
    chunks.append(cur)
    if len(chunks) == 1 and len(ranges) > 1:
        sys.exit(f'{f}: {len(ranges)} regions but no separators')
    if len(chunks) > len(ranges):
        chunks = chunks[1:] if not any(x.strip() for x in chunks[0]) else chunks
    for (a, b), ch in zip(ranges, chunks):
        repl.append((a, b, ch))
repl.sort(reverse=True)
for a, b, ch in repl:
    src[a-1:b] = ch
sys.stdout.write('\n'.join(src))
PY
}

check() {
  local name="$1"; shift
  splice "$@" > "$WORK/t.mac"
  ( cd "$WORK" && "$M1" -r -d t.mac >/dev/null 2>"$WORK/err" ) || { echo "FAIL $name (assembler)"; cat "$WORK/err"; return 1; }
  local got; got=$(sha256sum "$WORK/t.rim" | cut -d' ' -f1)
  if [ "$got" = "$SHA" ]; then echo "OK   $name"; else echo "DIFF $name ($got)"; return 1; fi
}

files=("$@"); [ ${#files[@]} -gt 0 ] || files=("$HERE"/*.lower.mac)
rc=0
for f in "${files[@]}"; do check "$(basename "$f")" "$f" || rc=1; done
[ ${#files[@]} -gt 1 ] && { check "all-together" "${files[@]}" || rc=1; }
exit $rc
