#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SESSION="${SESSION:-merlion-core-certification}"
RUN_ID="${RUN_ID:-merlion-core-$(date -u +%Y%m%dT%H%M%SZ)}"
LOG="${ROOT}/artifacts/merlion-core-runtime/${RUN_ID}.tmux.log"
mkdir -p "$(dirname "${LOG}")"

tmux has-session -t "${SESSION}" 2>/dev/null && {
  echo "BLOCKED: tmux session already exists: ${SESSION}" >&2
  exit 2
}

COMMAND=$(printf 'cd %q && RUN_ID=%q WAIT_FOR_ENTER=0 bash %q 2>&1 | tee %q' \
  "${ROOT}" "${RUN_ID}" "${ROOT}/scripts/run_merlion_core_certification.sh" "${LOG}")
tmux new-session -d -s "${SESSION}" "bash -lc ${COMMAND@Q}"

echo "SESSION=${SESSION}"
echo "RUN_ID=${RUN_ID}"
echo "LOG=${LOG}"
echo "ATTACH=tmux attach -t ${SESSION}"
echo "STOP=tmux send-keys -t ${SESSION} C-q"
