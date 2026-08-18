#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

usage() {
  echo "usage: bash tools/taj21.sh {preflight|smoke|baselines}"
}

runtime_python_cmd() {
  if [[ -n "${TAJ21_RUNTIME_PYTHON:-}" ]]; then
    printf '%s\0' "$TAJ21_RUNTIME_PYTHON"
  elif command -v uv >/dev/null 2>&1; then
    printf '%s\0' uv run --frozen python
  elif command -v python3 >/dev/null 2>&1; then
    printf '%s\0' python3
  else
    echo "TAJ21_RUNTIME=FAIL" >&2
    echo "REASON=uv/python3 is required" >&2
    exit 20
  fi
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
  smoke)
    RUN_ID="$(date +%Y%m%d-%H%M%S)"
    OUT="${TAJ21_SMOKE_ROOT:-$ROOT/runs/taj21-scientific-smoke/taj21-smoke-$RUN_ID}"
    GIT_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
    readarray -d '' -t PY_CMD < <(runtime_python_cmd)
    cd "$ROOT"

    PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "${PY_CMD[@]}" -m loto.cli_v3 campaign \
      --output "$OUT" \
      --synthetic \
      --synthetic-rows "${TAJ21_SMOKE_SYNTHETIC_ROWS:-32}" \
      --synthetic-seed "${TAJ21_SMOKE_SYNTHETIC_SEED:-7}" \
      --games numbers3 \
      --models logistic,pp-multinomial-dglm \
      --seeds 42 \
      --folds 1 \
      --test-size 1 \
      --min-train-size 12 \
      --holdout-size 0 \
      --gap 0 \
      --device cpu \
      --precision 32 \
      --max-trials 1 \
      --parallel-trials 1 \
      --max-steps 1 \
      --wall-time-seconds "${TAJ21_SMOKE_WALL_TIME_SECONDS:-300}" \
      --gpu-count 0 \
      --gpu-memory-bytes 0 \
      --git-commit "$GIT_COMMIT"

    PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "${PY_CMD[@]}" tools/evaluation/taj21_smoke_verify.py --root "$OUT"
    echo "TAJ21_SMOKE_ROOT=$OUT"
    ;;
  baselines)
    if [[ -z "${TAJ21_DATA_DIR:-}" ]]; then
      echo "TAJ21_BASELINE_REFERENCE=BLOCKED"
      echo "REASON=TAJ21_DATA_DIR must point to canonical six-game CSV directory"
      echo "SYNTHETIC_FALLBACK=FORBIDDEN"
      echo "HOLDOUT=CLOSED"
      echo "PROSPECTIVE=CLOSED"
      echo "PROMOTION=CLOSED"
      exit 21
    fi

    RUN_ID="$(date +%Y%m%d-%H%M%S)"
    OUT="${TAJ21_BASELINE_ROOT:-$ROOT/runs/taj21-baseline-reference/taj21-baselines-$RUN_ID}"
    GIT_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
    readarray -d '' -t PY_CMD < <(runtime_python_cmd)
    cd "$ROOT"
    echo "TAJ21_BASELINE_INPUT_DIR=$TAJ21_DATA_DIR"

    PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "${PY_CMD[@]}" tools/evaluation/taj21_baseline_campaign.py \
      --input-dir "$TAJ21_DATA_DIR" \
      --output "$OUT" \
      --git-commit "$GIT_COMMIT"

    PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "${PY_CMD[@]}" tools/evaluation/taj21_baseline_verify.py --root "$OUT"
    echo "TAJ21_BASELINE_ROOT=$OUT"
    ;;
  *)
    usage
    exit 2
    ;;
esac
