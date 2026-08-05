#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SESSION="${SESSION:-merlion-core-bootstrap}"
RUN_ID="${RUN_ID:-merlion-bootstrap-resume-$(date -u +%Y%m%dT%H%M%SZ)}"
LOG="${ROOT}/artifacts/merlion-bootstrap-launch/${RUN_ID}.log"
mkdir -p "$(dirname "${LOG}")"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "TMUX_SESSION_EXISTS=${SESSION}"
  exit 2
fi

COMMAND="cd $(printf '%q' "${ROOT}") && RUN_ID=$(printf '%q' "${RUN_ID}") "
COMMAND+="bash scripts/resume_merlion_core_bootstrap.sh 2>&1 | tee $(printf '%q' "${LOG}")"
tmux new-session -d -s "${SESSION}" "${COMMAND}"
echo "TMUX_SESSION=${SESSION}"
echo "RUN_ID=${RUN_ID}"
echo "LOG=${LOG}"
echo "ATTACH_COMMAND=tmux attach -t ${SESSION}"
