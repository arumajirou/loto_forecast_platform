#!/usr/bin/env bash
set -Eeuo pipefail

SESSION="${SKTIME_P10_TMUX_SESSION:-sktime-p10-canary-evaluation}"
ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
if tmux has-session -t "${SESSION}" 2>/dev/null; then
    echo "BLOCKED: tmux session already exists: ${SESSION}"
    exit 2
fi
tmux new-session -d -s "${SESSION}" \
    "cd '${ROOT}' && bash scripts/run_sktime_p10_certification.sh"
echo "TMUX_SESSION=${SESSION}"
echo "ATTACH_COMMAND=tmux attach -t ${SESSION}"
