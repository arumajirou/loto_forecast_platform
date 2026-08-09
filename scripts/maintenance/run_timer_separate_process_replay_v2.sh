#!/usr/bin/env bash
set -Eeuo pipefail

WORKTREE_DEFAULT='/home/az/worktrees/pr238-local-20260809T080814Z'
WORKTREE="${WORKTREE:-$WORKTREE_DEFAULT}"
INNER="$WORKTREE/scripts/maintenance/run_timer_separate_process_replay.sh"

[[ -f "$INNER" ]] || {
  echo "STOPPED SAFELY: missing inner replay harness: $INNER"
  exit 1
}

bash -n "$INNER"
command -v setsid >/dev/null 2>&1 || {
  echo 'STOPPED SAFELY: setsid is required for supervised replay cleanup'
  exit 1
}

setsid bash "$INNER" "$@" &
SUPERVISED_PID=$!

cleanup_group() {
  if kill -0 "$SUPERVISED_PID" 2>/dev/null; then
    kill -TERM -- "-$SUPERVISED_PID" 2>/dev/null || true
    sleep 1
    kill -KILL -- "-$SUPERVISED_PID" 2>/dev/null || true
  fi
}

trap cleanup_group EXIT INT TERM

set +e
wait "$SUPERVISED_PID"
RC=$?
set -e

if [[ "$RC" != '0' ]]; then
  cleanup_group
  echo "SUPERVISOR_STATUS=INNER_REPLAY_FAILED rc=$RC"
  exit "$RC"
fi

trap - EXIT INT TERM
echo 'SUPERVISOR_STATUS=PASS'
