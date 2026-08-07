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
bash docs/mlforecast/run_final_verification.sh "$@" 2>&1 | tee "$CAPTURE"
SOURCE_STATUS="${PIPESTATUS[0]}"
set -e
RUN_DIR="$(sed -n 's/^RUN_DIR=//p' "$CAPTURE" | tail -n 1)"
if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
  printf 'FINAL_GATE_FAILED: run directory was not emitted\n' >&2
  exit 7
fi

set +e
uv run --frozen -- python -m loto.mlforecast.final_gate --run-dir "$RUN_DIR"
GATE_STATUS=$?
set -e
if [[ "$GATE_STATUS" -ne 0 ]]; then
  printf 'FINAL_GATE_FAILED: evidence finalization returned %s\n' "$GATE_STATUS" >&2
  exit 7
fi
if [[ "$SOURCE_STATUS" -eq 0 ]]; then
  printf 'FINAL_GATE_CERTIFIED\nRUN_DIR=%s\n' "$RUN_DIR"
  exit 0
fi
printf 'FINAL_GATE_EVIDENCE_PRESERVED\nRUN_DIR=%s\n' "$RUN_DIR"
exit "$SOURCE_STATUS"
