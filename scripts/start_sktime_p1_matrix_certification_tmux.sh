#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
SESSION="${SKTIME_TMUX_SESSION:-sktime-p1-certification}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p1/${RUN_ID}}"

command -v tmux >/dev/null

if tmux has-session -t "${SESSION}" 2>/dev/null; then
    printf 'BLOCKED_ACTIVE_SESSION=%s\n' "${SESSION}"
    printf 'Attach with: tmux attach -t %q\n' "${SESSION}"
    exit 2
fi

mkdir -p "${RUN_DIR}"

tmux new-session \
    -d \
    -s "${SESSION}" \
    "cd $(printf '%q' "${ROOT}") && \
     SKTIME_NO_PAUSE=1 \
     SKTIME_RUN_ID=$(printf '%q' "${RUN_ID}") \
     SKTIME_RUN_DIR=$(printf '%q' "${RUN_DIR}") \
     bash scripts/run_sktime_p1_matrix_certification.sh"

printf 'SKTIME_P1_TMUX_STATUS=STARTED\n'
printf 'session=%s\n' "${SESSION}"
printf 'run_id=%s\n' "${RUN_ID}"
printf 'run_dir=%s\n' "${RUN_DIR}"
printf 'attach=tmux attach -t %q\n' "${SESSION}"
