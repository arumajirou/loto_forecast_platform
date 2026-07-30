#!/usr/bin/env bash
set -euo pipefail

cd /mnt/e/env/ts/loto_forecast_platform || exit 1
git rev-parse --show-toplevel

mkdir -p /mnt/e/env/ts/logs
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="/mnt/e/env/ts/logs/gpu-24h-campaign-${STAMP}.log"
PID_FILE="/mnt/e/env/ts/logs/gpu-24h-campaign-${STAMP}.pid"
LOCK="/tmp/loto-gpu-24h-campaign.lock"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "Another GPU 24h campaign is already running." >&2
  exit 3
fi

nohup env \
  CUDA_VISIBLE_DEVICES=0 \
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  OMP_NUM_THREADS="${CPU_THREADS:-8}" \
  MKL_NUM_THREADS="${CPU_THREADS:-8}" \
  OPENBLAS_NUM_THREADS="${CPU_THREADS:-8}" \
  NUMEXPR_NUM_THREADS="${CPU_THREADS:-8}" \
  TOKENIZERS_PARALLELISM=false \
  uv run python scripts/gpu_24h_campaign.py \
    --hours "${HOURS:-24}" \
    --per-model "${PER_MODEL:-200}" \
    --trial-timeout "${TRIAL_TIMEOUT:-7200}" \
    --cpu-threads "${CPU_THREADS:-8}" \
    --precision "${PRECISION:-32}" \
    --include-nixtla \
    --include-foundation \
  >"$LOG" 2>&1 &

PID=$!
echo "$PID" | tee "$PID_FILE"
echo "GPU_24H_PID=$PID"
echo "GPU_24H_LOG=$LOG"
