#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
DATA="${DATA:-${PROJECT_ROOT}/data/exports/numbers3/numbers3_n1.parquet}"
TARGET_DS="${1:?Usage: $0 TARGET_DS [OUTPUT_DIR]}"
OUTPUT="${2:-${PROJECT_ROOT}/prospective/numbers3-n1/locks}"
cd "$ROOT"
uv run loto-research shadow-lock \
  --project-root "$PROJECT_ROOT" \
  --data "$DATA" \
  --target-ds "$TARGET_DS" \
  --output "$OUTPUT"
echo "LOCK_OUTPUT=$OUTPUT"
