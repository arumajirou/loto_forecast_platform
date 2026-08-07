#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${1:-/mnt/e/env/ts/loto_forecast_platform}"
SNAPSHOT="${2:-/mnt/e/env/huggingface/hub/models--thuml--sundial-base-128m/snapshots/3212e42564493f520593e5414af4367fc4b49226}"

cd "$ROOT" || exit 1

RUN_LOG_ROOT="artifacts/sundial-provider-v2-launch"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
LAUNCH_DIR="$RUN_LOG_ROOT/$RUN_ID"
mkdir -p "$LAUNCH_DIR"
LOG="$LAUNCH_DIR/console.log"

finish() {
  rc=$?
  printf 'EXIT_CODE=%s\n' "$rc" | tee -a "$LOG"
  printf 'LAUNCH_DIR=%s\n' "$LAUNCH_DIR" | tee -a "$LOG"
  printf '\nEnterキーで終了します...'
  read -r _ || true
  exit "$rc"
}
trap finish EXIT

{
  printf 'SUNDIAL_PROVIDER_V2_CERTIFICATION_START\n'
  printf 'ROOT=%s\n' "$ROOT"
  printf 'SNAPSHOT=%s\n' "$SNAPSHOT"
  printf 'STARTED_AT=%s\n' "$(date --iso-8601=seconds)"

  test -f scripts/certify_sundial_provider_v2.py
  test -f scripts/run_sundial_provider.py
  test -f environments/sundial/pyproject.toml
  test -f environments/sundial/uv.lock
  test -d "$SNAPSHOT"
  command -v uv
  command -v nvidia-smi

  uv run --frozen python scripts/certify_sundial_provider_v2.py \
    --repo-root "$ROOT" \
    --snapshot "$SNAPSHOT" \
    --sample-counts 1,3,20,50,100 \
    --replay-samples 20 \
    --case-timeout 1800 \
    --seed 42
} 2>&1 | tee "$LOG"
