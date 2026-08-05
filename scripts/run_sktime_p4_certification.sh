#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
ACTUALS_CONFIG="${SKTIME_P4_ACTUALS_CONFIG:-${ROOT}/configs/sktime_campaign/holdout_actuals.json}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p4/${RUN_ID}}"
EVIDENCE_DIR="${RUN_DIR}/sealed-holdout-score"
LOG_DIR="${RUN_DIR}/logs"
MAIN_LOG="${LOG_DIR}/certification.log"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P4_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P4_RUN_DIR=%s\n' "${RUN_DIR}"
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

test -f "${ACTUALS_CONFIG}"
test -f "${ROOT}/scripts/run_sktime_p4_holdout_score.py"
test -f "${ROOT}/scripts/verify_sktime_p4_run.py"

P3_DIR="${SKTIME_P3_EVIDENCE_DIR:-}"
if [[ -z "${P3_DIR}" ]]; then
    P3_DIR="$({
        find "${ROOT}/artifacts/sktime-p3" \
            -mindepth 2 \
            -maxdepth 2 \
            -type d \
            -name oof-holdout-lock \
            -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
    } || true)"
fi
if [[ -z "${P3_DIR}" || ! -d "${P3_DIR}" ]]; then
    echo "BLOCKED: verified P3 evidence directory was not found"
    exit 2
fi

(
    cd "${P3_DIR}"
    sha256sum -c SHA256SUMS
)
python - "${P3_DIR}/response.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("status") != "PASS":
    raise SystemExit("P3 response status is not PASS")
if payload.get("holdout_status") != "PREDICTIONS_LOCKED_NOT_SCORED":
    raise SystemExit("P3 Holdout boundary mismatch")
if payload.get("promotion_status") != "NOT_PROMOTED":
    raise SystemExit("P3 promotion boundary mismatch")
PY

PREDICTION_LOCK="${P3_DIR}/HOLDOUT_PREDICTION_LOCK.json"
P3_SHA256SUMS="${P3_DIR}/SHA256SUMS"
test -s "${PREDICTION_LOCK}"
test -s "${P3_SHA256SUMS}"

readarray -t TIMES < <(
    python - \
        "${PREDICTION_LOCK}" \
        "${SKTIME_P4_REVEALED_AT_UTC:-}" \
        "${SKTIME_P4_SCORED_AT_UTC:-}" <<'PY'
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

lock = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
sealed = datetime.strptime(
    lock["sealed_at_utc"],
    "%Y-%m-%dT%H:%M:%SZ",
).replace(tzinfo=UTC)
now = datetime.now(UTC).replace(microsecond=0)
revealed = (
    datetime.strptime(sys.argv[2], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if sys.argv[2]
    else max(now, sealed + timedelta(seconds=1))
)
scored = (
    datetime.strptime(sys.argv[3], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if sys.argv[3]
    else max(
        datetime.now(UTC).replace(microsecond=0),
        revealed + timedelta(seconds=1),
    )
)
if revealed <= sealed:
    raise SystemExit("revealed_at_utc must be after P3 sealed_at_utc")
if scored < revealed:
    raise SystemExit("scored_at_utc must not precede revealed_at_utc")
print(revealed.strftime("%Y-%m-%dT%H:%M:%SZ"))
print(scored.strftime("%Y-%m-%dT%H:%M:%SZ"))
PY
)
REVEALED_AT_UTC="${TIMES[0]}"
SCORED_AT_UTC="${TIMES[1]}"

CONFIG_SHA256="$(sha256sum "${ACTUALS_CONFIG}" | awk '{print $1}')"
GIT_COMMIT="$(git rev-parse HEAD)"
CODE_SHA_INPUT="${RUN_DIR}/CODE_SHA256_INPUT"
(
    cd "${ROOT}"
    sha256sum \
        src/loto/sktime_campaign/holdout_scoring.py \
        src/loto/sktime_campaign/holdout_artifacts.py \
        src/loto/sktime_campaign/benchmark.py \
        src/loto/sktime_campaign/rolling_origin.py \
        scripts/run_sktime_p4_holdout_score.py \
        scripts/verify_sktime_p4_run.py
) | tee "${CODE_SHA_INPUT}"
CODE_SHA256="$(sha256sum "${CODE_SHA_INPUT}" | awk '{print $1}')"

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'git_commit=%s\n' "${GIT_COMMIT}"
    printf 'config_sha256=%s\n' "${CONFIG_SHA256}"
    printf 'code_sha256=%s\n' "${CODE_SHA256}"
    printf 'p3_evidence_dir=%s\n' "${P3_DIR}"
    printf 'prediction_lock_sha256=%s\n' \
        "$(sha256sum "${PREDICTION_LOCK}" | awk '{print $1}')"
    printf 'p3_sha256sums_sha256=%s\n' \
        "$(sha256sum "${P3_SHA256SUMS}" | awk '{print $1}')"
    printf 'revealed_at_utc=%s\n' "${REVEALED_AT_UTC}"
    printf 'scored_at_utc=%s\n' "${SCORED_AT_UTC}"
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
    "${ROOT}/src/loto/sktime_campaign/holdout_scoring.py"
    "${ROOT}/src/loto/sktime_campaign/holdout_artifacts.py"
    "${ROOT}/scripts/run_sktime_p4_holdout_score.py"
    "${ROOT}/scripts/verify_sktime_p4_run.py"
    "${ROOT}/tests/sktime_campaign/test_holdout_scoring.py"
    "${ROOT}/tests/sktime_campaign/test_holdout_artifacts.py"
)
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q \
    "${ROOT}/tests/sktime_campaign/test_holdout_scoring.py" \
    "${ROOT}/tests/sktime_campaign/test_holdout_artifacts.py" \
    | tee "${RUN_DIR}/focused-pytest.log"

COMMON_ARGS=(
    --actuals-config "${ACTUALS_CONFIG}"
    --prediction-lock "${PREDICTION_LOCK}"
    --p3-sha256sums "${P3_SHA256SUMS}"
    --output "${EVIDENCE_DIR}"
    --run-id "${RUN_ID}"
    --git-commit "${GIT_COMMIT}"
    --code-sha256 "${CODE_SHA256}"
    --config-sha256 "${CONFIG_SHA256}"
    --revealed-at-utc "${REVEALED_AT_UTC}"
    --scored-at-utc "${SCORED_AT_UTC}"
)

set +e
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_p4_holdout_score.py" \
    "${COMMON_ARGS[@]}" \
    | tee "${LOG_DIR}/scoring.log"
SCORING_RC=${PIPESTATUS[0]}
set -e

VERIFY_ARGS=("${COMMON_ARGS[@]}")
if [[ "${SCORING_RC}" -ne 0 ]]; then
    VERIFY_ARGS+=(--allow-nonpass)
fi
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p4_run.py" \
    "${VERIFY_ARGS[@]}" \
    | tee "${LOG_DIR}/verification.log"

(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

if [[ "${SCORING_RC}" -ne 0 ]]; then
    echo "SKTIME_P4_STATUS=EVIDENCE_VERIFIED_NONPASS"
    exit "${SCORING_RC}"
fi

echo "SKTIME_P4_STATUS=VERIFIED"
