#!/usr/bin/env bash
set -Eeuo pipefail

ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ENV_DIR/../.." && pwd)"
PYTHON="$ENV_DIR/.venv/bin/python"
COMMAND="${1:-}"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    printf 'BLOCKED: required environment variable is unset: %s\n' "$name" >&2
    exit 2
  fi
}

if [[ ! -x "$PYTHON" ]]; then
  printf 'BLOCKED: isolated Python does not exist: %s\n' "$PYTHON" >&2
  exit 2
fi

case "$COMMAND" in
  prepare)
    require_env HISTORY_ROOT
    require_env SNAPSHOT
    require_env EXPECTED_HEAD
    require_env WORK_ROOT
    exec "$PYTHON" "$REPO_ROOT/scripts/prepare_toto2_4m_target_host.py" \
      --history-root "$HISTORY_ROOT" \
      --snapshot "$SNAPSHOT" \
      --isolated-python "$PYTHON" \
      --expected-head "$EXPECTED_HEAD" \
      --output-root "$WORK_ROOT"
    ;;
  run)
    require_env SNAPSHOT
    require_env WORK_ROOT
    require_env LOCK_REVIEW
    mkdir -p "$WORK_ROOT/matrix-runs"
    exec "$PYTHON" \
      "$REPO_ROOT/scripts/run_toto2_4m_target_host_certification.py" \
      --matrix-manifest \
      "$REPO_ROOT/configs/toto2_campaign/formal_runtime_matrix.json" \
      --requests-root "$WORK_ROOT/requests" \
      --snapshot "$SNAPSHOT" \
      --isolated-python "$PYTHON" \
      --lock-review "$LOCK_REVIEW" \
      --output-root "$WORK_ROOT/matrix-runs"
    ;;
  verify)
    require_env ARCHIVE
    require_env ARCHIVE_SHA256_FILE
    require_env VERIFY_OUTPUT
    exec "$PYTHON" "$REPO_ROOT/scripts/verify_toto2_4m_target_host.py" \
      --archive "$ARCHIVE" \
      --archive-sha256-file "$ARCHIVE_SHA256_FILE" \
      --output "$VERIFY_OUTPUT"
    ;;
  *)
    cat >&2 <<'EOF'
Usage:
  target-host-certification.sh prepare
  target-host-certification.sh run
  target-host-certification.sh verify

prepare requires: HISTORY_ROOT SNAPSHOT EXPECTED_HEAD WORK_ROOT
run requires: SNAPSHOT WORK_ROOT LOCK_REVIEW
verify requires: ARCHIVE ARCHIVE_SHA256_FILE VERIFY_OUTPUT
EOF
    exit 2
    ;;
esac
