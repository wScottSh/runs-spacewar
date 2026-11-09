#!/usr/bin/env bash
# Every check of the port: the image compiled from RUNS, the mutation gate,
# and each RUNS routine against SIMH running the original. Run from anywhere.
set -eo pipefail
here=$(cd "$(dirname "$0")" && pwd)
cd "$here/.."
uv run -q python "$here/runsc.py" | tail -1
uv run -q python "$here/check_compiled.py" --sample 8000 | tail -1     # the full gate (about 20 minutes) runs by hand
PYTHONPATH=tools uv run -q python "$here/check_square_root.py"
PYTHONPATH=tools uv run -q python "$here/check_multiply.py"
PYTHONPATH=tools uv run -q python "$here/check_divide.py"
PYTHONPATH=tools uv run -q python "$here/check_sincos.py" 20000
PYTHONPATH=tools uv run -q python "$here/check_tunables.py"
PYTHONPATH=tools uv run -q python "$here/check_calc_routines.py" 1000 | tail -4
PYTHONPATH=tools uv run -q python "$here/check_outline_compiler.py" | grep -v "^  "
PYTHONPATH=tools uv run -q python "$here/check_spaceship.py" 1000
PYTHONPATH=tools uv run -q python "$here/check_spaceship.py" 300 moved | head -1
PYTHONPATH=tools uv run -q python "$here/check_heavens.py" 1000
PYTHONPATH=tools uv run -q python "$here/check_frame.py" 300 | grep -v fired
PYTHONPATH=tools uv run -q python "$here/check_frame.py" 300 poison | grep -v fired
PYTHONPATH=tools uv run -q python "$here/check_game.py" 3000 3000
