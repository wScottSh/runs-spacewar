#!/usr/bin/env bash
# Assemble Ground Truth into the oracle .rim and assert its hash.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORACLE_SHA=8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf
mkdir -p "$ROOT/build"
[ -x "$ROOT/build/macro1" ] || gcc -O2 -w -o "$ROOT/build/macro1" "$ROOT/tools/macro1.c"
cp "$ROOT/source/spacewar3.1_complete.txt" "$ROOT/build/oracle.mac"
"$ROOT/build/macro1" -r -d "$ROOT/build/oracle.mac" >/dev/null
echo "$ORACLE_SHA  $ROOT/build/oracle.rim" | sha256sum -c -
