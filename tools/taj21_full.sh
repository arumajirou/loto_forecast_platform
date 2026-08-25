#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${TAJ21_DATA_DIR:-}" ]]; then
  echo "TAJ21_FULL_OOF=BLOCKED"
  echo "REASON=TAJ21_DATA_DIR must point to canonical six-game CSV directory"
  echo "SYNTHETIC_FALLBACK=FORBIDDEN"
  echo "HOLDOUT=CLOSED"
  echo "PROSPECTIVE=CLOSED"
  echo "PROMOTION=CLOSED"
  exit 21
fi

if [[ -n "${TAJ21_RUNTIME_PYTHON:-}" ]]; then
  PY_CMD=("$TAJ21_RUNTIME_PYTHON")
elif command -v uv >/dev/null 2>&1; then
  PY_CMD=(uv run --frozen python)
elif command -v python3 >/dev/null 2>&1; then
  PY_CMD=(python3)
else
  echo "TAJ21_FULL_OOF=BLOCKED"
  echo "REASON=uv or python3 is required"
  exit 20
fi

RUN_ID="${TAJ21_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
OUT="${TAJ21_FULL_ROOT:-$ROOT/runs/taj21-full-oof/taj21-full-$RUN_ID}"
CHECKPOINT_DIR="${TAJ21_CHECKPOINT_DIR:-${OUT}.checkpoints}"
GIT_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"

cd "$ROOT"

echo "TAJ21_FULL_RUN_ID=$RUN_ID"
echo "TAJ21_FULL_GIT_COMMIT=$GIT_COMMIT"
echo "TAJ21_FULL_INPUT_DIR=$TAJ21_DATA_DIR"
echo "TAJ21_FULL_OUTPUT=$OUT"
echo "TAJ21_FULL_CHECKPOINT_DIR=$CHECKPOINT_DIR"
echo "TAJ21_RESUME_HINT=rerun with the same TAJ21_RUN_ID or TAJ21_FULL_ROOT/TAJ21_CHECKPOINT_DIR"

PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  "${PY_CMD[@]}" tools/evaluation/taj21_full_campaign.py \
  --input-dir "$TAJ21_DATA_DIR" \
  --output "$OUT" \
  --checkpoint-dir "$CHECKPOINT_DIR" \
  --git-commit "$GIT_COMMIT" \
  --device "${TAJ21_DEVICE:-auto}" \
  --precision "${TAJ21_PRECISION:-32}" \
  --max-trials "${TAJ21_MAX_TRIALS:-10}" \
  --parallel-trials "${TAJ21_PARALLEL_TRIALS:-1}" \
  --max-steps "${TAJ21_MAX_STEPS:-50}" \
  --wall-time-seconds "${TAJ21_WALL_TIME_SECONDS:-1800}" \
  --gpu-count "${TAJ21_GPU_COUNT:-0}" \
  --gpu-memory-bytes "${TAJ21_GPU_MEMORY_BYTES:-0}"

PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  "${PY_CMD[@]}" tools/evaluation/taj21_full_verify.py \
  --root "$OUT" \
  --git-commit "$GIT_COMMIT"

echo "TAJ21_FULL_OOF_FORMAL=PASS"
echo "HOLDOUT=CLOSED"
echo "PROSPECTIVE=CLOSED"
echo "PROMOTION=CLOSED"
echo "TAJ21_FULL_ROOT=$OUT"
echo "TAJ21_FULL_CHECKPOINT_DIR=$CHECKPOINT_DIR"
