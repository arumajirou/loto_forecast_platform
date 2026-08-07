#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${1:-/mnt/e/env/ts/loto_forecast_platform}"
cd "$ROOT"
export LOTO_HARNESS_CONFIG="${LOTO_HARNESS_CONFIG:-configs/harness/gateway.yaml}"
exec uv run --extra harness loto-harness serve
