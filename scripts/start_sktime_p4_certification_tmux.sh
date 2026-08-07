#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
SESSION="${SKTIME_P4_TMUX_SESSION:-sktime-p4-certification}"

command -v tmux >/dev/null

if tmux has-session -t "${SESSION}" 2>/dev/null; then
    echo "BLOCKED: tmux session already exists: ${SESSION}"
    echo "Attach with: tmux attach -t ${SESSION}"
    exit 2
fi

tmux new-session -d -s "${SESSION}" \
    "cd '${ROOT}' && SKTIME_NO_PAUSE=1 bash scripts/run_sktime_p4_certification.sh"

echo "SKTIME_P4_TMUX_SESSION=${SESSION}"
echo "Attach with: tmux attach -t ${SESSION}"
