#!/usr/bin/env bash
set -uo pipefail

REPO_DIR="${REPO_DIR:-/mnt/e/env/ts/loto_forecast_platform}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner-loto}"
WRAPPER_LOG_DIR="${WRAPPER_LOG_DIR:-$RUNNER_DIR/_setup_logs}"
mkdir -p "$WRAPPER_LOG_DIR"

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
LOG_FILE="$WRAPPER_LOG_DIR/interactive-bootstrap-$RUN_ID.log"
EXIT_FILE="$WRAPPER_LOG_DIR/interactive-bootstrap-$RUN_ID.exitcode"

pause_terminal() {
  if [[ -r /dev/tty ]]; then
    read -r -p "Enterキーでターミナルに戻ります..." _ </dev/tty || true
  fi
}

rc=0
(
  set -Eeuo pipefail
  cd "$REPO_DIR"

  if [[ ! -f scripts/self_hosted_runner/bootstrap_linux.sh ]]; then
    echo "FAILED: bootstrap_linux.sh が現在のbranchにありません。"
    echo "PR #146が未mergeなら次を実行してください:"
    echo "  git fetch origin"
    echo "  git switch agent/self-hosted-gpu-ci-v1"
    echo "  git pull --ff-only origin agent/self-hosted-gpu-ci-v1"
    exit 30
  fi

  if [[ -z "${RUNNER_DOWNLOAD_URL:-}" || "$RUNNER_DOWNLOAD_URL" == *"GitHub画面"* || "$RUNNER_DOWNLOAD_URL" == *"PASTE_"* ]]; then
    echo "FAILED: RUNNER_DOWNLOAD_URLをGitHub画面の実値へ置換してください。"
    exit 31
  fi

  if [[ -z "${RUNNER_SHA256:-}" || "$RUNNER_SHA256" == *"GitHub画面"* || "$RUNNER_SHA256" == *"PASTE_"* ]]; then
    echo "FAILED: RUNNER_SHA256をGitHub画面の実値へ置換してください。"
    exit 32
  fi

  PAUSE_ON_EXIT=0 bash scripts/self_hosted_runner/bootstrap_linux.sh
) > >(tee -a "$LOG_FILE") 2>&1 || rc=$?

printf '%s\n' "$rc" > "$EXIT_FILE"
printf '\nwrapper_status=%s\nwrapper_exit_code=%s\nlog=%s\nexit_code_file=%s\n' \
  "$([[ $rc -eq 0 ]] && echo VERIFIED || echo FAILED)" \
  "$rc" \
  "$LOG_FILE" \
  "$EXIT_FILE"

pause_terminal

# Interactive safety contract: never terminate the caller's shell through `set -e`.
# The actual bootstrap status is retained in EXIT_FILE and printed above.
exit 0
