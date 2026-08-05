#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
SESSION="${SKTIME_P8_TMUX_SESSION:-sktime-p8-registry-cas}"

tmux has-session -t "${SESSION}" 2>/dev/null && {
    echo "BLOCKED: tmux session already exists: ${SESSION}"
    exit 2
}

tmux new-session -d -s "${SESSION}" \
    "cd '${ROOT}' && bash scripts/run_sktime_p8_certification.sh"

echo "TMUX_SESSION=${SESSION}"
echo "Attach with: tmux attach -t ${SESSION}"
