#!/usr/bin/env bash
set -Eeuo pipefail

# Resilient Numbers4 DB -> NeuralForecast AutoModel campaign runner.
# Usage:
#   ./scripts/run_numbers4_nf_automodels.sh dry-run [DB_PATH]
#   ./scripts/run_numbers4_nf_automodels.sh smoke   [DB_PATH]
#   ./scripts/run_numbers4_nf_automodels.sh full    [DB_PATH]
# Set LOTO_NO_WAIT=1 for unattended execution.

ROOT="${LOTO_PROJECT_ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
MODE="${1:-dry-run}"
DB_PATH="${2:-${LOTO_NUMBERS4_DB:-${ROOT}/runs/numbers4-research-20260803-204223/data/features/datasets.sqlite3}}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT="${LOTO_OUTPUT_DIR:-${ROOT}/runs/numbers4-neuralforecast-automodel-${MODE}-${RUN_ID}}"
LOG_DIR="${OUT}/logs"
LOG="${LOG_DIR}/run.log"
EXIT_FILE="${LOG_DIR}/exit_code.txt"

mkdir -p "${LOG_DIR}"

on_exit() {
    code=$?
    printf '%s\n' "${code}" >"${EXIT_FILE}"
    printf '\nEXIT_CODE=%s\nOUTPUT=%s\nLOG=%s\n' "${code}" "${OUT}" "${LOG}" | tee -a "${LOG}"
    if [[ "${LOTO_NO_WAIT:-0}" != "1" && -t 0 ]]; then
        printf '終了するにはEnterを押してください。'
        read -r _ || true
    fi
    exit "${code}"
}
trap on_exit EXIT

exec > >(tee -a "${LOG}") 2>&1

cd "${ROOT}" || exit 1
printf 'STARTED_AT=%s\nMODE=%s\nDB_PATH=%s\nOUTPUT=%s\n' \
    "$(date --iso-8601=seconds)" "${MODE}" "${DB_PATH}" "${OUT}"

test -f "${DB_PATH}"

# Do not mutate dependencies on every run. Prepare once with:
#   uv sync --extra full
if [[ "${MODE}" != "dry-run" ]]; then
    uv run python - <<'PY'
import importlib.util
import sys
required = ("neuralforecast", "optuna")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print("MISSING_RUNTIME_DEPENDENCIES=" + ",".join(missing), file=sys.stderr)
    print("Run: uv sync --extra full", file=sys.stderr)
    raise SystemExit(3)
PY
fi

COMMON=(
    neuralforecast automodel-run
    --db-url "${DB_PATH}"
    --table normalized_draws
    --game numbers4
    --layout wide
    --time-col draw_no
    --value-columns d1,d2,d3,d4
    --output "${OUT}"
    --freq 1
    --h 1
    --cpus "${LOTO_CPUS_PER_MODEL:-8}"
    --gpus "${LOTO_GPUS_PER_MODEL:-1}"
    --workers "${LOTO_WORKERS:-8}"
    --max-gpu-jobs "${LOTO_MAX_GPU_JOBS:-1}"
    --seed "${LOTO_SEED:-42}"
)

case "${MODE}" in
    dry-run)
        uv run loto "${COMMON[@]}" \
            --models all \
            --backend optuna \
            --num-samples 1 \
            --val-size 20 \
            --dry-run
        ;;
    smoke)
        uv run loto "${COMMON[@]}" \
            --models nf-auto-dlinear,nf-auto-nlinear \
            --model-config configs/neuralforecast/numbers4_automodel_smoke.json \
            --backend optuna \
            --num-samples 1 \
            --val-size 20 \
            --local-scaler-type robust \
            --local-static-scaler-type standard \
            --save-models
        ;;
    full)
        uv run loto "${COMMON[@]}" \
            --models all \
            --backend optuna \
            --num-samples "${LOTO_NUM_SAMPLES:-10}" \
            --parallel-trials "${LOTO_PARALLEL_TRIALS:-1}" \
            --val-size "${LOTO_VAL_SIZE:-50}" \
            --local-scaler-type "${LOTO_LOCAL_SCALER:-robust}" \
            --local-static-scaler-type "${LOTO_LOCAL_STATIC_SCALER:-standard}" \
            --save-models
        ;;
    *)
        printf 'Unknown mode: %s (expected dry-run, smoke, or full)\n' "${MODE}" >&2
        exit 2
        ;;
esac

printf 'FINISHED_AT=%s\n' "$(date --iso-8601=seconds)"
