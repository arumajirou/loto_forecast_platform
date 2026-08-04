#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(
  cd "$(dirname "$0")/../.." &&
  pwd
)"

cd "${ROOT}"

CONFIG_DIR="configs/generated/tcn-v2/interaction"
LOG_DIR="artifacts/numbers3/tcn-v2-interaction-logs"

mkdir -p "${LOG_DIR}"

for config in "${CONFIG_DIR}"/interaction-*.yaml
do
  name="$(
    basename "${config}" .yaml
  )"

  log="${LOG_DIR}/${name}.log"

  echo
  echo "START=${name}"
  echo "TIME=$(date --iso-8601=seconds)"

  CUDA_VISIBLE_DEVICES=0 \
  uv run python \
    scripts/experiments/run_numbers3_n1_tcn_exhaustive.py \
    --config "${config}" \
    --mode evaluate \
    --skip-model-artifacts \
    2>&1 |
  tee "${log}"

  echo "DONE=${name}"
  echo "TIME=$(date --iso-8601=seconds)"
done
