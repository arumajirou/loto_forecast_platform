#!/usr/bin/env bash
set -Eeuo pipefail

# Execute and verify the Numbers4 database NeuralForecast campaign.
# Usage:
#   ./scripts/run_numbers4_nf_runtime_verification.sh cpu-smoke [DB_PATH]
#   ./scripts/run_numbers4_nf_runtime_verification.sh gpu-smoke [DB_PATH]
#   ./scripts/run_numbers4_nf_runtime_verification.sh gpu-full  [DB_PATH]

ROOT="${LOTO_PROJECT_ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
MODE="${1:-gpu-smoke}"
DEFAULT_DB="${ROOT}/runs/numbers4-research-20260803-204223/data/features/datasets.sqlite3"
DB_PATH="${2:-${LOTO_NUMBERS4_DB:-${DEFAULT_DB}}}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT="${LOTO_OUTPUT_DIR:-${ROOT}/runs/numbers4-neuralforecast-runtime-${MODE}-${RUN_ID}}"

case "${MODE}" in
    cpu-smoke)
        CAMPAIGN_MODE="smoke"
        EXPECTED_MODELS=2
        GPUS=0
        VERIFY_MODE=(--require-cpu)
        ;;
    gpu-smoke)
        CAMPAIGN_MODE="smoke"
        EXPECTED_MODELS=2
        GPUS=1
        VERIFY_MODE=(--require-gpu)
        ;;
    gpu-full)
        CAMPAIGN_MODE="full"
        EXPECTED_MODELS=36
        GPUS=1
        VERIFY_MODE=(--require-gpu)
        ;;
    *)
        printf 'Unknown mode: %s\n' "${MODE}" >&2
        exit 2
        ;;
esac

cd "${ROOT}" || exit 1
printf 'RUNTIME_VERIFICATION_START\nMODE=%s\nDB_PATH=%s\nOUTPUT=%s\n' \
    "${MODE}" "${DB_PATH}" "${OUT}"

test -f "${DB_PATH}"

LOTO_NO_WAIT=1 \
LOTO_OUTPUT_DIR="${OUT}" \
LOTO_GPUS_PER_MODEL="${GPUS}" \
LOTO_CPUS_PER_MODEL="${LOTO_CPUS_PER_MODEL:-8}" \
LOTO_WORKERS="${LOTO_WORKERS:-8}" \
LOTO_MAX_GPU_JOBS="${LOTO_MAX_GPU_JOBS:-1}" \
LOTO_SEED="${LOTO_SEED:-1}" \
bash scripts/run_numbers4_nf_automodels.sh "${CAMPAIGN_MODE}" "${DB_PATH}"

uv run python scripts/verify_neuralforecast_db_runtime.py \
    "${OUT}" \
    --expected-model-count "${EXPECTED_MODELS}" \
    "${VERIFY_MODE[@]}"

printf 'RUNTIME_VERIFICATION_FINISHED\nOUTPUT=%s\n' "${OUT}"
if [[ "${LOTO_NO_WAIT:-0}" != "1" && -t 0 ]]; then
    printf '終了するにはEnterを押してください。'
    read -r _ || true
fi
