#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
CONFIG="${SKTIME_P5_LOCK_CONFIG:-${ROOT}/configs/sktime_campaign/prospective_shadow.json}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p5-lock/${RUN_ID}}"
EVIDENCE_DIR="${RUN_DIR}/prospective-shadow-lock"
LOG_DIR="${RUN_DIR}/logs"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P5_LOCK_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P5_LOCK_RUN_DIR=%s\n' "${RUN_DIR}"
    if [[ "${SKTIME_NO_PAUSE:-0}" != "1" && -t 0 ]]; then
        read -r -p "Press Enter to close..." _
    fi
    exit "${rc}"
}
trap finish EXIT
exec > >(tee -a "${LOG_DIR}/certification.log") 2>&1

cd "${ROOT}"
command -v git
command -v uv
command -v sha256sum

test -s "${CONFIG}"
test -s "${ROOT}/scripts/run_sktime_p5_lock.py"
test -s "${ROOT}/scripts/verify_sktime_p5_lock.py"

P4_DIR="${SKTIME_P4_EVIDENCE_DIR:-}"
if [[ -z "${P4_DIR}" ]]; then
    P4_DIR="$({
        find "${ROOT}/artifacts/sktime-p4" \
            -mindepth 2 \
            -maxdepth 2 \
            -type d \
            -name sealed-holdout-score \
            -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
    } || true)"
fi
if [[ -z "${P4_DIR}" || ! -d "${P4_DIR}" ]]; then
    echo "BLOCKED: verified P4 evidence directory was not found"
    exit 2
fi

(
    cd "${P4_DIR}"
    sha256sum -c SHA256SUMS
)

readarray -t P4_FIELDS < <(
    python - "${P4_DIR}/response.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("status") != "PASS":
    raise SystemExit("P4 response status is not PASS")
if payload.get("promotion_status") != (
    "HOLDOUT_SCORED_NOT_PROMOTED_PROSPECTIVE_REQUIRED"
):
    raise SystemExit("P4 promotion boundary mismatch")
if payload.get("model_execution") is not False:
    raise SystemExit("P4 incorrectly claims model execution")
if payload.get("retraining") is not False:
    raise SystemExit("P4 incorrectly claims retraining")
if payload.get("reprediction") is not False:
    raise SystemExit("P4 incorrectly claims reprediction")
selected = payload.get("selected_oof_candidate_id")
if not selected:
    raise SystemExit("P4 selected OOF candidate is missing")
print(selected)
PY
)
P4_SELECTED="${P4_FIELDS[0]}"

P4_SHA256SUMS="${P4_DIR}/SHA256SUMS"
P4_RESPONSE="${P4_DIR}/response.json"
P4_AGGREGATES="${P4_DIR}/HOLDOUT_CANDIDATE_AGGREGATES.json"
test -s "${P4_SHA256SUMS}"
test -s "${P4_RESPONSE}"
test -s "${P4_AGGREGATES}"

CONFIG_SHA256="$(sha256sum "${CONFIG}" | awk '{print $1}')"
GIT_COMMIT="$(git rev-parse HEAD)"
CODE_SHA_INPUT="${RUN_DIR}/CODE_SHA256_INPUT"
(
    cd "${ROOT}"
    sha256sum \
        src/loto/sktime_campaign/prospective.py \
        src/loto/sktime_campaign/prospective_artifacts.py \
        src/loto/sktime_campaign/benchmark.py \
        src/loto/sktime_campaign/matrix.py \
        scripts/run_sktime_p5_lock.py \
        scripts/verify_sktime_p5_lock.py
) | tee "${CODE_SHA_INPUT}"
CODE_SHA256="$(sha256sum "${CODE_SHA_INPUT}" | awk '{print $1}')"
P4_ARTIFACT_SHA256="$(sha256sum "${P4_SHA256SUMS}" | awk '{print $1}')"
P4_RESPONSE_SHA256="$(sha256sum "${P4_RESPONSE}" | awk '{print $1}')"
P4_SUMS_SHA256="${P4_ARTIFACT_SHA256}"
P4_AGGREGATES_SHA256="$(sha256sum "${P4_AGGREGATES}" | awk '{print $1}')"

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'git_commit=%s\n' "${GIT_COMMIT}"
    printf 'config_sha256=%s\n' "${CONFIG_SHA256}"
    printf 'code_sha256=%s\n' "${CODE_SHA256}"
    printf 'p4_evidence_dir=%s\n' "${P4_DIR}"
    printf 'p4_artifact_sha256=%s\n' "${P4_ARTIFACT_SHA256}"
    printf 'p4_selected_oof_candidate_id=%s\n' "${P4_SELECTED}"
    printf 'max_workers=8\n'
    printf 'device=cpu\n'
    printf 'cpu_fallback=false\n'
    printf 'uv_version=%s\n' "$(uv --version)"
} | tee "${RUN_DIR}/RUN_METADATA.txt"

uv lock --project "${ENV_DIR}"
test -s "${ENV_DIR}/uv.lock"
sha256sum "${ENV_DIR}/uv.lock" | tee "${RUN_DIR}/UV_LOCK_SHA256"
uv sync --project "${ENV_DIR}" --group dev --frozen

export PYTHONPATH="${ROOT}/src:${ROOT}/scripts"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign/prospective.py"
    "${ROOT}/src/loto/sktime_campaign/prospective_artifacts.py"
    "${ROOT}/scripts/run_sktime_p5_lock.py"
    "${ROOT}/scripts/verify_sktime_p5_lock.py"
    "${ROOT}/tests/sktime_campaign/test_prospective.py"
    "${ROOT}/tests/sktime_campaign/test_prospective_artifacts.py"
)
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q \
    "${ROOT}/tests/sktime_campaign/test_prospective.py" \
    "${ROOT}/tests/sktime_campaign/test_prospective_artifacts.py" \
    | tee "${RUN_DIR}/focused-pytest.log"

COMMON_ARGS=(
    --config "${CONFIG}"
    --output "${EVIDENCE_DIR}"
    --run-id "${RUN_ID}"
    --git-commit "${GIT_COMMIT}"
    --code-sha256 "${CODE_SHA256}"
    --config-sha256 "${CONFIG_SHA256}"
    --p4-artifact-sha256 "${P4_ARTIFACT_SHA256}"
    --p4-selected-candidate "${P4_SELECTED}"
    --p4-response-sha256 "${P4_RESPONSE_SHA256}"
    --p4-sha256sums-sha256 "${P4_SUMS_SHA256}"
    --p4-aggregates-sha256 "${P4_AGGREGATES_SHA256}"
)
if [[ -n "${SKTIME_P5_SEALED_AT_UTC:-}" ]]; then
    COMMON_ARGS+=(--sealed-at-utc "${SKTIME_P5_SEALED_AT_UTC}")
fi

set +e
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_p5_lock.py" \
    "${COMMON_ARGS[@]}" \
    | tee "${LOG_DIR}/prediction-lock.log"
LOCK_RC=${PIPESTATUS[0]}
set -e

VERIFY_ARGS=("${COMMON_ARGS[@]}")
if [[ "${LOCK_RC}" -ne 0 ]]; then
    VERIFY_ARGS+=(--allow-nonpass)
fi
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p5_lock.py" \
    "${VERIFY_ARGS[@]}" \
    | tee "${LOG_DIR}/verification.log"

(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

if [[ "${LOCK_RC}" -ne 0 ]]; then
    echo "SKTIME_P5_LOCK_STATUS=EVIDENCE_VERIFIED_NONPASS"
    exit "${LOCK_RC}"
fi

echo "SKTIME_P5_LOCK_STATUS=VERIFIED"
