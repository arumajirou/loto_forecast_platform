#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
CONFIG="${SKTIME_P3_CONFIG:-${ROOT}/configs/sktime_campaign/rolling_origin_oof.json}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p3/${RUN_ID}}"
EVIDENCE_DIR="${RUN_DIR}/oof-holdout-lock"
LOG_DIR="${RUN_DIR}/logs"
MAIN_LOG="${LOG_DIR}/certification.log"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P3_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P3_RUN_DIR=%s\n' "${RUN_DIR}"
    if [[ "${SKTIME_NO_PAUSE:-0}" != "1" && -t 0 ]]; then
        read -r -p "Press Enter to close..." _
    fi
    exit "${rc}"
}
trap finish EXIT
exec > >(tee -a "${MAIN_LOG}") 2>&1

cd "${ROOT}"
command -v git
command -v uv
command -v sha256sum

test -f "${CONFIG}"
test -f "${ROOT}/scripts/run_sktime_p3_oof.py"
test -f "${ROOT}/scripts/verify_sktime_p3_run.py"

P2_DIR="${SKTIME_P2_BENCHMARK_DIR:-}"
if [[ -z "${P2_DIR}" ]]; then
    P2_DIR="$({
        find "${ROOT}/artifacts/sktime-p2" \
            -mindepth 2 \
            -maxdepth 2 \
            -type d \
            -name benchmark \
            -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
    } || true)"
fi
if [[ -z "${P2_DIR}" || ! -d "${P2_DIR}" ]]; then
    echo "BLOCKED: verified P2 benchmark directory was not found"
    exit 2
fi

(
    cd "${P2_DIR}"
    sha256sum -c SHA256SUMS
)
python - "${P2_DIR}/response.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("status") != "PASS":
    raise SystemExit("P2 response status is not PASS")
if payload.get("promotion_status") != "VALIDATION_ONLY_NOT_PROMOTED":
    raise SystemExit("P2 promotion boundary mismatch")
PY

VALIDATION_ARTIFACT_SHA256="$(sha256sum "${P2_DIR}/SHA256SUMS" | awk '{print $1}')"
CONFIG_SHA256="$(sha256sum "${CONFIG}" | awk '{print $1}')"
GIT_COMMIT="$(git rev-parse HEAD)"

CODE_SHA_INPUT="${RUN_DIR}/CODE_SHA256_INPUT"
(
    cd "${ROOT}"
    sha256sum \
        src/loto/sktime_campaign/rolling_origin.py \
        src/loto/sktime_campaign/rolling_artifacts.py \
        src/loto/sktime_campaign/benchmark.py \
        src/loto/sktime_campaign/matrix.py \
        src/loto/sktime_campaign/protocol.py
) | tee "${CODE_SHA_INPUT}"
CODE_SHA256="$(sha256sum "${CODE_SHA_INPUT}" | awk '{print $1}')"

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'git_commit=%s\n' "${GIT_COMMIT}"
    printf 'config_sha256=%s\n' "${CONFIG_SHA256}"
    printf 'code_sha256=%s\n' "${CODE_SHA256}"
    printf 'p2_benchmark_dir=%s\n' "${P2_DIR}"
    printf 'validation_artifact_sha256=%s\n' "${VALIDATION_ARTIFACT_SHA256}"
    printf 'uv_version=%s\n' "$(uv --version)"
} | tee "${RUN_DIR}/RUN_METADATA.txt"

uv lock --project "${ENV_DIR}"
test -s "${ENV_DIR}/uv.lock"
sha256sum "${ENV_DIR}/uv.lock" | tee "${RUN_DIR}/UV_LOCK_SHA256"
uv sync --project "${ENV_DIR}" --group dev --frozen

export PYTHONPATH="${ROOT}/src"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign"
    "${ROOT}/scripts/run_sktime_p3_oof.py"
    "${ROOT}/scripts/verify_sktime_p3_run.py"
    "${ROOT}/tests/sktime_campaign"
)
uv run --project "${ENV_DIR}" --group dev python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q "${ROOT}/tests/sktime_campaign" \
    | tee "${RUN_DIR}/focused-pytest.log"

COMMON_ARGS=(
    --config "${CONFIG}"
    --output "${EVIDENCE_DIR}"
    --run-id "${RUN_ID}"
    --git-commit "${GIT_COMMIT}"
    --code-sha256 "${CODE_SHA256}"
    --config-sha256 "${CONFIG_SHA256}"
    --validation-artifact-sha256 "${VALIDATION_ARTIFACT_SHA256}"
)

set +e
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_p3_oof.py" \
    "${COMMON_ARGS[@]}" \
    | tee "${LOG_DIR}/provider.log"
PROVIDER_RC=${PIPESTATUS[0]}
set -e

VERIFY_ARGS=("${COMMON_ARGS[@]}")
if [[ "${PROVIDER_RC}" -ne 0 ]]; then
    VERIFY_ARGS+=(--allow-nonpass)
fi
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p3_run.py" \
    "${VERIFY_ARGS[@]}" \
    | tee "${LOG_DIR}/verification.log"

(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

if [[ "${PROVIDER_RC}" -ne 0 ]]; then
    echo "SKTIME_P3_STATUS=EVIDENCE_VERIFIED_NONPASS"
    exit "${PROVIDER_RC}"
fi

echo "SKTIME_P3_STATUS=VERIFIED"
