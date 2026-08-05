#!/usr/bin/env bash
set -Eeuo pipefail

if ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi
cd "$ROOT"

WHEEL="${1:-$ROOT/artifacts/mlforecast-wheel/mlforecast-1.1.0-py3-none-any.whl}"
OUTPUT_ROOT="${2:-$ROOT/artifacts/mlforecast-runtime-certification}"
EXPECTED_SHA256="0043190f540510979c7709bb69267caa9ac325a11fa49298cf3425307200e748"

if [[ ! -f "$WHEEL" ]]; then
  printf 'BLOCKED: wheel not found: %s\n' "$WHEEL" >&2
  exit 2
fi

ACTUAL_SHA256="$(sha256sum "$WHEEL" | awk '{print $1}')"
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  printf 'FAILED: wheel SHA-256 mismatch\nEXPECTED=%s\nACTUAL=%s\n' \
    "$EXPECTED_SHA256" "$ACTUAL_SHA256" >&2
  exit 3
fi

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

uv run \
  --frozen \
  --with "$WHEEL" \
  -- \
  python -m loto.mlforecast.certify \
  --wheel "$WHEEL" \
  --output-root "$OUTPUT_ROOT" \
  --seed 1 \
  --auto-trials 2
