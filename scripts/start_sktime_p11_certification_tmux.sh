#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
SESSION="${SKTIME_P11_TMUX_SESSION:-sktime-p11-primary-promotion-authorization}"
COMMAND="cd $(printf '%q' "${ROOT}") && bash scripts/run_sktime_p11_certification.sh"
if tmux has-session -t "${SESSION}" 2>/dev/null; then
    echo "BLOCKED: tmux session already exists: ${SESSION}"
    exit 2
fi
tmux new-session -d -s "${SESSION}" "${COMMAND}"
echo "TMUX_SESSION=${SESSION}"
echo "ATTACH_COMMAND=tmux attach -t ${SESSION}"
