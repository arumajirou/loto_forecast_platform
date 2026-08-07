#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SESSION="${SESSION:-merlion-core-certification}"
RUN_ID="${RUN_ID:-merlion-core-$(date -u +%Y%m%dT%H%M%SZ)}"
LOG="${ROOT}/artifacts/merlion-core-runtime/${RUN_ID}.tmux.log"
LOCK_COMMIT_REPORT="${MERLION_LOCK_COMMIT_REPORT:-}"
mkdir -p "$(dirname "${LOG}")"

test -n "${LOCK_COMMIT_REPORT}" || {
  echo "BLOCKED: MERLION_LOCK_COMMIT_REPORT is required" >&2
  exit 2
}
test -f "${LOCK_COMMIT_REPORT}" || {
  echo "BLOCKED: lock commit report not found: ${LOCK_COMMIT_REPORT}" >&2
  exit 2
}
tmux has-session -t "${SESSION}" 2>/dev/null && {
  echo "BLOCKED: tmux session already exists: ${SESSION}" >&2
  exit 2
}

COMMAND=$(printf \
  'cd %q && RUN_ID=%q WAIT_FOR_ENTER=0 MERLION_LOCK_COMMIT_REPORT=%q bash %q 2>&1 | tee %q' \
  "${ROOT}" \
  "${RUN_ID}" \
  "${LOCK_COMMIT_REPORT}" \
  "${ROOT}/scripts/run_merlion_core_certification.sh" \
  "${LOG}")
tmux new-session -d -s "${SESSION}" "bash -lc ${COMMAND@Q}"

echo "SESSION=${SESSION}"
echo "RUN_ID=${RUN_ID}"
echo "LOCK_COMMIT_REPORT=${LOCK_COMMIT_REPORT}"
echo "LOG=${LOG}"
echo "ATTACH=tmux attach -t ${SESSION}"
echo "STOP=tmux send-keys -t ${SESSION} C-q"
