#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

usage() {
  echo "usage: bash tools/taj21.sh preflight"
}

case "${1:-}" in
  preflight)
    RUN_ID="$(date +%Y%m%d-%H%M%S)"
    OUT="${TAJ21_PREFLIGHT_ROOT:-$ROOT/runs/taj21-scientific-preflight/taj21-preflight-$RUN_ID}"
    cd "$ROOT"
    PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON_BIN" tools/evaluation/taj21_scientific_preflight.py --output "$OUT"
    echo "TAJ21_PREFLIGHT_ROOT=$OUT"
    ;;
  *)
    usage
    exit 2
    ;;
esac
