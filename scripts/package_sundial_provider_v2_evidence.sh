#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${1:-/mnt/e/env/ts/loto_forecast_platform}"
RUN_DIR="${2:-}"
EXPECTED_COMMIT="${3:-}"
EXPECTED_BRANCH="${EXPECTED_BRANCH:-feat/sundial-probabilistic-provider-v2}"
export UV_FROZEN=1

cd "$ROOT" || exit 1

if [[ -z "$RUN_DIR" ]]; then
  test -f artifacts/sundial-provider-v2/LATEST
  RUN_DIR="$(cat artifacts/sundial-provider-v2/LATEST)"
fi
if [[ -z "$EXPECTED_COMMIT" ]]; then
  EXPECTED_COMMIT="$(git rev-parse HEAD)"
fi

CURRENT_COMMIT="$(git rev-parse HEAD)"
CURRENT_BRANCH="$(git branch --show-current)"
test "$CURRENT_COMMIT" = "$EXPECTED_COMMIT"
test "$CURRENT_BRANCH" = "$EXPECTED_BRANCH"
git diff --quiet
git diff --cached --quiet

test -d "$RUN_DIR"
test -f "$RUN_DIR/status.txt"
test -f "$RUN_DIR/environment.json"
test -f "$RUN_DIR/certification-summary.json"
grep -Fx 'SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS' "$RUN_DIR/status.txt"

LOG_ROOT="artifacts/sundial-provider-v2-package-launch"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
LAUNCH_DIR="$LOG_ROOT/$RUN_ID"
mkdir -p "$LAUNCH_DIR"
LOG="$LAUNCH_DIR/console.log"

finish() {
  rc=$?
  printf 'EXIT_CODE=%s\n' "$rc" | tee -a "$LOG"
  printf 'LAUNCH_DIR=%s\n' "$LAUNCH_DIR" | tee -a "$LOG"
  if [[ -t 0 ]]; then
    printf '\nEnterキーで終了します...'
    read -r _ || true
  fi
  exit "$rc"
}
trap finish EXIT

{
  printf 'SUNDIAL_PROVIDER_V2_EVIDENCE_PACKAGE_START\n'
  printf 'ROOT=%s\n' "$ROOT"
  printf 'RUN_DIR=%s\n' "$RUN_DIR"
  printf 'EXPECTED_COMMIT=%s\n' "$EXPECTED_COMMIT"
  printf 'EXPECTED_BRANCH=%s\n' "$EXPECTED_BRANCH"

  test -f scripts/verify_sundial_provider_v2_semantics.py
  test -f scripts/verify_sundial_provider_v2_evidence.py

  uv run --frozen python scripts/verify_sundial_provider_v2_semantics.py \
    --run-dir "$RUN_DIR" \
    --repo-root "$ROOT"

  uv run --frozen python scripts/verify_sundial_provider_v2_evidence.py \
    --run-dir "$RUN_DIR" \
    --repo-root "$ROOT" \
    --expected-commit "$EXPECTED_COMMIT" \
    --expected-branch "$EXPECTED_BRANCH" \
    --archive
} 2>&1 | tee "$LOG"
