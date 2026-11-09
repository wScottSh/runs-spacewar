#!/usr/bin/env bash
# Run a check on a copy of runs/ with one edit, to show the check sees it.
# Usage: tools/mutate.sh FILE 'sed-expression' CHECK [ARGS...]
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
file=$1 expr=$2 check=$3; shift 3
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -r "$here/runs/." "$tmp/"
sed -i "$expr" "$tmp/$file"
if cmp -s "$here/runs/$file" "$tmp/$file"; then echo "mutation did not apply"; exit 2; fi
diff "$here/runs/$file" "$tmp/$file" || true
cd "$here"
RUNS_SOURCE="$tmp" uv run python "$here/tools/$check" "$@"
