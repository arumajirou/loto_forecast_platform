#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
SESSION="${SKTIME_P5_MONITOR_SESSION:-sktime-p5-monitor}"

command -v tmux >/dev/null
if tmux has-session -t "${SESSION}" 2>/dev/null; then
    echo "BLOCKED: tmux session already exists: ${SESSION}"
    exit 2
fi

tmux new-session -d -s "${SESSION}" \
    "cd '${ROOT}' && SKTIME_NO_PAUSE=1 bash scripts/run_sktime_p5_monitor_certification.sh; rc=\$?; echo SKTIME_P5_MONITOR_FINAL_RC=\$rc; exec bash"

echo "STARTED_SESSION=${SESSION}"
echo "ATTACH_COMMAND=tmux attach -t ${SESSION}"
