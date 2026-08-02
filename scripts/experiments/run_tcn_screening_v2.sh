#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT}"
mkdir -p artifacts/numbers3/tcn-v2-screening-logs
for cfg in configs/generated/tcn-v2/screening/*.yaml; do
  name="$(basename "${cfg}" .yaml)"
  CUDA_VISIBLE_DEVICES=0 uv run python \
    scripts/experiments/run_numbers3_n1_tcn_exhaustive.py \
    --config "${cfg}" --mode evaluate --skip-model-artifacts \
    2>&1 | tee "artifacts/numbers3/tcn-v2-screening-logs/${name}.log"
done
