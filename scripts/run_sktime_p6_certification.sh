#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
POLICY_CONFIG="${SKTIME_P6_POLICY_CONFIG:-${ROOT}/configs/sktime_campaign/promotion_policy.json}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p6/${RUN_ID}}"
EVIDENCE_DIR="${RUN_DIR}/manual-promotion-gate"
LOG_DIR="${RUN_DIR}/logs"
MAIN_LOG="${LOG_DIR}/certification.log"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"
RESOLVED_REQUEST="${RUN_DIR}/resolved-request.json"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P6_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P6_RUN_DIR=%s\n' "${RUN_DIR}"
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

test -f "${POLICY_CONFIG}"

required_vars=(
    SKTIME_P0_EVIDENCE_DIR
    SKTIME_P1_EVIDENCE_DIR
    SKTIME_P2_EVIDENCE_DIR
    SKTIME_P3_EVIDENCE_DIR
    SKTIME_P4_EVIDENCE_DIR
    SKTIME_P5_MONITOR_DIRS
)
for name in "${required_vars[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        echo "BLOCKED: required environment variable is missing: ${name}"
        exit 2
    fi
done

IFS=':' read -r -a P5_DIRS <<< "${SKTIME_P5_MONITOR_DIRS}"
if [[ "${#P5_DIRS[@]}" -lt 1 ]]; then
    echo "BLOCKED: no P5 monitor directories were supplied"
    exit 2
fi

for directory in \
    "${SKTIME_P0_EVIDENCE_DIR}" \
    "${SKTIME_P1_EVIDENCE_DIR}" \
    "${SKTIME_P2_EVIDENCE_DIR}" \
    "${SKTIME_P3_EVIDENCE_DIR}" \
    "${SKTIME_P4_EVIDENCE_DIR}" \
    "${P5_DIRS[@]}"; do
    test -d "${directory}"
    (
        cd "${directory}"
        sha256sum -c SHA256SUMS
    )
done

CONFIG_SHA256="$(sha256sum "${POLICY_CONFIG}" | awk '{print $1}')"
GIT_COMMIT="$(git rev-parse HEAD)"

CODE_SHA_INPUT="${RUN_DIR}/CODE_SHA256_INPUT"
(
    cd "${ROOT}"
    sha256sum \
        src/loto/sktime_campaign/promotion_gate.py \
        src/loto/sktime_campaign/promotion_artifacts.py \
        scripts/build_sktime_p6_request.py \
        scripts/run_sktime_p6_promotion_gate.py \
        scripts/verify_sktime_p6_run.py
) | tee "${CODE_SHA_INPUT}"
CODE_SHA256="$(sha256sum "${CODE_SHA_INPUT}" | awk '{print $1}')"

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'git_commit=%s\n' "${GIT_COMMIT}"
    printf 'config_sha256=%s\n' "${CONFIG_SHA256}"
    printf 'code_sha256=%s\n' "${CODE_SHA256}"
    printf 'p5_monitor_count=%s\n' "${#P5_DIRS[@]}"
    printf 'uv_version=%s\n' "$(uv --version)"
} | tee "${RUN_DIR}/RUN_METADATA.txt"

uv lock --project "${ENV_DIR}"
test -s "${ENV_DIR}/uv.lock"
sha256sum "${ENV_DIR}/uv.lock" | tee "${RUN_DIR}/UV_LOCK_SHA256"
uv sync --project "${ENV_DIR}" --group dev --frozen

export PYTHONPATH="${ROOT}/src"

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign/promotion_gate.py"
    "${ROOT}/src/loto/sktime_campaign/promotion_artifacts.py"
    "${ROOT}/scripts/build_sktime_p6_request.py"
    "${ROOT}/scripts/run_sktime_p6_promotion_gate.py"
    "${ROOT}/scripts/verify_sktime_p6_run.py"
    "${ROOT}/tests/sktime_campaign/test_promotion_gate.py"
    "${ROOT}/tests/sktime_campaign/test_promotion_artifacts.py"
)
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q \
    "${ROOT}/tests/sktime_campaign/test_promotion_gate.py" \
    "${ROOT}/tests/sktime_campaign/test_promotion_artifacts.py" \
    | tee "${RUN_DIR}/focused-pytest.log"

BUILD_ARGS=(
    --policy-config "${POLICY_CONFIG}"
    --output "${RESOLVED_REQUEST}"
    --run-id "${RUN_ID}"
    --git-commit "${GIT_COMMIT}"
    --code-sha256 "${CODE_SHA256}"
    --config-sha256 "${CONFIG_SHA256}"
    --p0-dir "${SKTIME_P0_EVIDENCE_DIR}"
    --p1-dir "${SKTIME_P1_EVIDENCE_DIR}"
    --p2-dir "${SKTIME_P2_EVIDENCE_DIR}"
    --p3-dir "${SKTIME_P3_EVIDENCE_DIR}"
    --p4-dir "${SKTIME_P4_EVIDENCE_DIR}"
)
for directory in "${P5_DIRS[@]}"; do
    BUILD_ARGS+=(--p5-monitor-dir "${directory}")
done

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/build_sktime_p6_request.py" \
    "${BUILD_ARGS[@]}" \
    | tee "${LOG_DIR}/request-builder.log"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_p6_promotion_gate.py" \
    --request "${RESOLVED_REQUEST}" \
    --output "${EVIDENCE_DIR}" \
    | tee "${LOG_DIR}/provider.log"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p6_run.py" \
    --request "${RESOLVED_REQUEST}" \
    --output "${EVIDENCE_DIR}" \
    | tee "${LOG_DIR}/verification.log"

(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

cat "${EVIDENCE_DIR}/PROMOTION_DECISION.json"
echo "SKTIME_P6_STATUS=VERIFIED_NOT_PROMOTED"
