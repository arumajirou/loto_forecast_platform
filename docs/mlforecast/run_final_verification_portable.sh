#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$ROOT"

CAPTURE="$(mktemp)"
cleanup() { rm -f -- "$CAPTURE"; }
trap cleanup EXIT

set +e
bash docs/mlforecast/run_final_verification_complete.sh "$@" 2>&1 | tee "$CAPTURE"
SOURCE_STATUS="${PIPESTATUS[0]}"
set -e
RUN_DIR="$(sed -n 's/^RUN_DIR=//p' "$CAPTURE" | tail -n 1)"
if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
  printf 'FINAL_EVIDENCE_FAILED: run directory was not emitted\n' >&2
  exit 8
fi

RUN_ID="$(basename "$RUN_DIR")"
OUTPUT_ROOT="${MLFORECAST_FINAL_EVIDENCE_ROOT:-$ROOT/artifacts/mlforecast-final-evidence}"
ZIP="$OUTPUT_ROOT/$RUN_ID.final-evidence.zip"
SIDECAR="$ZIP.sha256"
REPORT="$OUTPUT_ROOT/$RUN_ID.final-evidence.verification.json"

set +e
uv run --frozen -- python -m loto.mlforecast.final_evidence \
  --build --run-dir "$RUN_DIR" --output-dir "$OUTPUT_ROOT"
BUILD_STATUS=$?
set -e
if [[ "$BUILD_STATUS" -ne 0 ]]; then
  printf 'FINAL_EVIDENCE_FAILED: bundle construction returned %s\n' "$BUILD_STATUS" >&2
  exit 8
fi

set +e
uv run --frozen -- python -m loto.mlforecast.final_evidence \
  --verify --zip "$ZIP" --sha256 "$SIDECAR" --report "$REPORT"
VERIFY_STATUS=$?
set -e
if [[ "$VERIFY_STATUS" -ne 0 ]]; then
  printf 'FINAL_EVIDENCE_FAILED: independent verification returned %s\n' \
    "$VERIFY_STATUS" >&2
  exit 9
fi

printf 'FINAL_EVIDENCE_ZIP=%s\n' "$ZIP"
printf 'FINAL_EVIDENCE_SHA256=%s\n' "$SIDECAR"
printf 'FINAL_EVIDENCE_REPORT=%s\n' "$REPORT"
if [[ "$SOURCE_STATUS" -eq 0 ]]; then
  printf 'FINAL_EVIDENCE_CERTIFIED\nRUN_DIR=%s\n' "$RUN_DIR"
  exit 0
fi
printf 'FINAL_EVIDENCE_PRESERVED\nRUN_DIR=%s\n' "$RUN_DIR"
exit "$SOURCE_STATUS"
