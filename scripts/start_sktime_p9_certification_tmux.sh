#!/usr/bin/env bash
set -Eeuo pipefail
SESSION="${SKTIME_P9_TMUX_SESSION:-sktime-p9-shadow-canary}"
ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
if tmux has-session -t "${SESSION}" 2>/dev/null; then
    echo "BLOCKED: tmux session already exists: ${SESSION}"
    exit 2
fi
tmux new-session -d -s "${SESSION}" \
    "cd '${ROOT}' && bash scripts/run_sktime_p9_certification.sh"
echo "SESSION=${SESSION}"
echo "ATTACH=tmux attach -t ${SESSION}"
