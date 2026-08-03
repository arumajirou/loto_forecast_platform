#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
cd "$ROOT"

# Prevent nested BLAS/OpenMP oversubscription. GPU-capable backends are
# serialized by max_gpu_jobs=1 while CPU-light tasks fill the remaining slots.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export XLA_PYTHON_CLIENT_PREALLOCATE="${XLA_PYTHON_CLIENT_PREALLOCATE:-false}"
export XLA_PYTHON_CLIENT_MEM_FRACTION="${XLA_PYTHON_CLIENT_MEM_FRACTION:-0.85}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

if pgrep -af '[l]oto3 probabilistic run' >/dev/null; then
    echo "ERROR: another probabilistic run is active" >&2
    pgrep -af '[l]oto3 probabilistic run' >&2 || true
    exit 3
fi

if test -f "$ROOT/.env.ppl-notify"; then
    # shellcheck disable=SC1091
    source "$ROOT/.env.ppl-notify"
fi

uv run python scripts/probabilistic/verify_acceleration.py \
  --config configs/probabilistic/native_fast_gpu_dashboard.yaml

mkdir -p artifacts/probabilistic-notifications
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$ROOT/artifacts/probabilistic-notifications/fast-gpu-${STAMP}.log"
OUTPUT_ROOT="$ROOT/runs/probabilistic-native-fast-gpu"

set +e
setsid uv run loto3 probabilistic run \
  --config configs/probabilistic/native_fast_gpu_dashboard.yaml \
  > >(tee "$LOG") 2>&1 &
RUNNER_PID=$!
set -e

cleanup() {
    local signal="${1:-INT}"
    if kill -0 "$RUNNER_PID" 2>/dev/null; then
        kill -"$signal" -- "-$RUNNER_PID" 2>/dev/null || \
          kill -"$signal" "$RUNNER_PID" 2>/dev/null || true
    fi
}
trap 'cleanup INT' INT TERM HUP

echo "RUNNER_PID=$RUNNER_PID"
echo "LOG=$LOG"

set +e
uv run python scripts/probabilistic/progress_dashboard.py \
  --output-root "$OUTPUT_ROOT" \
  --runner-pid "$RUNNER_PID" \
  --interval 2
DASHBOARD_STATUS=$?
wait "$RUNNER_PID"
RUNNER_STATUS=$?
set -e

echo "dashboard_exit_code=$DASHBOARD_STATUS"
echo "runner_exit_code=$RUNNER_STATUS"
echo "log=$LOG"
exit "$RUNNER_STATUS"
