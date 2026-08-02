#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-${PROJECT_ROOT}/artifacts/numbers3}"
DATA="${DATA:-${PROJECT_ROOT}/data/exports/numbers3/numbers3_n1.parquet}"
OUTPUT="${OUTPUT:-${PROJECT_ROOT}/releases/numbers3-n1-research-closure-$(date +%Y%m%d-%H%M%S)}"
cd "$ROOT"
uv run loto-research close \
  --project-root "$PROJECT_ROOT" \
  --artifact-root "$ARTIFACT_ROOT" \
  --data "$DATA" \
  --output "$OUTPUT" \
  --zip
uv run loto-research verify "$OUTPUT"
echo "OUTPUT=$OUTPUT"
echo "ZIP=${OUTPUT}.zip"
