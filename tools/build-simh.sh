#!/usr/bin/env bash
# Build a headless SIMH pdp1 simulator into build/pdp1 from an open-simh checkout.
# Usage: tools/build-simh.sh [SIMH_SRC]   (default: $SIMH_SRC)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIMH="${1:-${SIMH_SRC:?pass the open-simh source dir or set SIMH_SRC}}"
OUT="$ROOT/build/pdp1"
mkdir -p "$ROOT/build"
[ -x "$OUT" ] && { echo "$OUT"; exit 0; }
gcc -O2 -w -D_GNU_SOURCE \
  -I"$SIMH" -I"$SIMH/PDP1" \
  "$SIMH"/scp.c "$SIMH"/sim_console.c "$SIMH"/sim_fio.c "$SIMH"/sim_timer.c \
  "$SIMH"/sim_sock.c "$SIMH"/sim_tmxr.c "$SIMH"/sim_ether.c "$SIMH"/sim_tape.c \
  "$SIMH"/sim_disk.c "$SIMH"/sim_serial.c "$SIMH"/sim_video.c "$SIMH"/sim_imd.c \
  "$SIMH"/sim_card.c \
  "$SIMH"/PDP1/pdp1_lp.c "$SIMH"/PDP1/pdp1_cpu.c "$SIMH"/PDP1/pdp1_stddev.c \
  "$SIMH"/PDP1/pdp1_sys.c "$SIMH"/PDP1/pdp1_dt.c "$SIMH"/PDP1/pdp1_drm.c \
  "$SIMH"/PDP1/pdp1_clk.c "$SIMH"/PDP1/pdp1_dcs.c \
  -o "$OUT" -lm -lpthread
echo "$OUT"
