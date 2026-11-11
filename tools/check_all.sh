#!/usr/bin/env bash
# Every check of the port: the image compiled from RUNS, the mutation gate,
# and each RUNS routine against SIMH running the original. Run from anywhere.
#
# The two builds run first (every check reads build/runs or build/minskytron);
# then every check runs at once. No check writes a shared file: SIMH reads its
# script on stdin and check_compiled builds its mutants in temp dirs. Each
# step's output is printed in the order below with its wall time.
set -o pipefail
here=$(cd "$(dirname "$0")" && pwd)
cd "$here/.."
export here
log=$(mktemp -d)
trap 'rm -rf "$log"' EXIT

builds=(
  'uv run -q python "$here/runsc.py" | tail -1'
  # The second program: the same compiler builds Minskytron's image, and its RUNS plots the original's points.
  'RUNS_PROGRAM=programs/minskytron uv run -q python "$here/runsc.py" | tail -1'
)
checks=(
  'uv run -q python "$here/check_compiled.py" --sample 8000 | tail -1'     # the full gate runs by hand
  'uv run -q python "$here/check_declarations.py"'
  'PYTHONPATH=tools uv run -q python "$here/check_square_root.py"'
  'PYTHONPATH=tools uv run -q python "$here/check_multiply.py"'
  'PYTHONPATH=tools uv run -q python "$here/check_divide.py"'
  'PYTHONPATH=tools uv run -q python "$here/check_sincos.py" 20000'
  'PYTHONPATH=tools uv run -q python "$here/check_tunables.py"'
  'PYTHONPATH=tools uv run -q python "$here/check_calc_routines.py" 1000 | tail -4'
  'PYTHONPATH=tools uv run -q python "$here/check_outline_compiler.py" | grep -v "^  "'
  'PYTHONPATH=tools uv run -q python "$here/check_spaceship.py" 1000'
  'PYTHONPATH=tools uv run -q python "$here/check_spaceship.py" 300 moved | head -1'
  'PYTHONPATH=tools uv run -q python "$here/check_heavens.py" 1000'
  'PYTHONPATH=tools uv run -q python "$here/check_frame.py" 300 | grep -v fired'
  'PYTHONPATH=tools uv run -q python "$here/check_frame.py" 300 poison | grep -v fired'
  'PYTHONPATH=tools uv run -q python "$here/check_frame.py" 300 alone | grep -v fired'
  'PYTHONPATH=tools uv run -q python "$here/check_game.py" 3000 3000'
  'PYTHONPATH=tools uv run -q python "$here/check_minskytron.py" | tail -1'
  # The spec states every decision; its examples must run on this evaluator.
  'uv run -q python "${RUNS_SPEC:-$here/../../runs-spec}/tools/check_examples.py" "${RUNS_SPEC:-$here/../../runs-spec}" . | tail -1'
)

# Runs each command at once, then prints each one's output and time in order;
# fails if any failed.
phase() {
  local name=$1; shift
  local cmds=("$@") i start=$SECONDS failed=0
  for i in "${!cmds[@]}"; do
    ( s=$SECONDS; bash -o pipefail -c "${cmds[$i]}" >"$log/$name.$i" 2>&1; rc=$?
      echo "$rc $((SECONDS - s))" >"$log/$name.$i.rc" ) &
  done
  wait
  for i in "${!cmds[@]}"; do
    read -r rc secs <"$log/$name.$i.rc"
    printf '== %s (%ds)%s\n' "${cmds[$i]%% |*}" "$secs" "$([ "$rc" = 0 ] || echo " FAILED: exit $rc")"
    cat "$log/$name.$i"
    [ "$rc" = 0 ] || failed=1
  done
  echo "== $name: $((SECONDS - start))s"
  return $failed
}

total=$SECONDS
phase builds "${builds[@]}" || exit 1
phase checks "${checks[@]}" || exit 1
echo "== all passed in $((SECONDS - total))s"
