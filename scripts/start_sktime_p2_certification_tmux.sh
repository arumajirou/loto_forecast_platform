#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
SESSION="${SKTIME_TMUX_SESSION:-sktime-p2-certification}"

command -v tmux >/dev/null
cd "${ROOT}"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
    printf 'BLOCKED: tmux session already exists: %s\n' "${SESSION}" >&2
    exit 2
fi

tmux new-session \
    -d \
    -s "${SESSION}" \
    "cd '${ROOT}' && SKTIME_NO_PAUSE=1 bash scripts/run_sktime_p2_certification.sh"

printf 'SKTIME_P2_TMUX_SESSION=%s\n' "${SESSION}"
printf 'Attach with: tmux attach -t %q\n' "${SESSION}"
