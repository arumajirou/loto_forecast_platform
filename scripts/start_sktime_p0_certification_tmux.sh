#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
SESSION="${SKTIME_TMUX_SESSION:-sktime-p0-certification}"
SCRIPT="${ROOT}/scripts/run_sktime_p0_certification.sh"

cd "${ROOT}"
test -f "${SCRIPT}"
bash -n "${SCRIPT}"
command -v tmux

if tmux has-session -t "${SESSION}" 2>/dev/null; then
    printf 'SKTIME_TMUX_STATUS=ALREADY_RUNNING\n'
    printf 'session=%s\n' "${SESSION}"
    tmux list-panes -t "${SESSION}" -F '#{pane_pid} #{pane_current_command}'
    exit 20
fi

tmux new-session \
    -d \
    -s "${SESSION}" \
    "cd '${ROOT}' && export SKTIME_NO_PAUSE=1 && exec bash '${SCRIPT}'"

sleep 2

printf 'SKTIME_TMUX_STATUS=STARTED\n'
printf 'session=%s\n' "${SESSION}"
printf 'attach=tmux attach -t %s\n' "${SESSION}"
printf 'logs=%s/artifacts/sktime-p0/<run-id>/logs/certification.log\n' "${ROOT}"
