#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
DEFAULT_POLICY="${ROOT}/configs/sktime_campaign/registry_transaction_policy.json"
POLICY_CONFIG="${SKTIME_P8_POLICY_CONFIG:-${DEFAULT_POLICY}}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p8/${RUN_ID}}"
EVIDENCE_DIR="${RUN_DIR}/file-registry-cas"
LOG_DIR="${RUN_DIR}/logs"
MAIN_LOG="${LOG_DIR}/certification.log"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"
RESOLVED_REQUEST="${RUN_DIR}/resolved-request.json"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P8_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P8_RUN_DIR=%s\n' "${RUN_DIR}"
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
    SKTIME_P8_P7_EVIDENCE_DIR
    SKTIME_P8_REGISTRY_STATE
    SKTIME_P8_REQUESTED_AT_UTC
    SKTIME_P8_TRANSACTION_NONCE
)
for name in "${required_vars[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        echo "BLOCKED: required environment variable is missing: ${name}"
        exit 2
    fi
done

test -d "${SKTIME_P8_P7_EVIDENCE_DIR}"
test -f "${SKTIME_P8_REGISTRY_STATE}"
(
    cd "${SKTIME_P8_P7_EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

GIT_COMMIT="$(git rev-parse HEAD)"
CONFIG_SHA256="$(sha256sum "${POLICY_CONFIG}" | awk '{print $1}')"
CODE_SHA_INPUT="${RUN_DIR}/CODE_SHA256_INPUT"
(
    cd "${ROOT}"
    sha256sum \
        src/loto/sktime_campaign/registry_transaction.py \
        src/loto/sktime_campaign/registry_artifacts.py \
        scripts/build_sktime_p8_request.py \
        scripts/run_sktime_p8_transaction.py \
        scripts/verify_sktime_p8_run.py
) | tee "${CODE_SHA_INPUT}"
CODE_SHA256="$(sha256sum "${CODE_SHA_INPUT}" | awk '{print $1}')"

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'git_commit=%s\n' "${GIT_COMMIT}"
    printf 'config_sha256=%s\n' "${CONFIG_SHA256}"
    printf 'code_sha256=%s\n' "${CODE_SHA256}"
    printf 'registry_state=%s\n' "${SKTIME_P8_REGISTRY_STATE}"
    printf 'uv_version=%s\n' "$(uv --version)"
} | tee "${RUN_DIR}/RUN_METADATA.txt"

uv lock --project "${ENV_DIR}"
test -s "${ENV_DIR}/uv.lock"
sha256sum "${ENV_DIR}/uv.lock" | tee "${RUN_DIR}/UV_LOCK_SHA256"
uv sync --project "${ENV_DIR}" --group dev --frozen

export PYTHONPATH="${ROOT}/src:${ROOT}/tests/sktime_campaign"
CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign/registry_transaction.py"
    "${ROOT}/src/loto/sktime_campaign/registry_artifacts.py"
    "${ROOT}/scripts/bootstrap_sktime_p8_registry.py"
    "${ROOT}/scripts/build_sktime_p8_request.py"
    "${ROOT}/scripts/run_sktime_p8_transaction.py"
    "${ROOT}/scripts/verify_sktime_p8_run.py"
    "${ROOT}/tests/sktime_campaign/test_registry_transaction.py"
    "${ROOT}/tests/sktime_campaign/test_registry_artifacts.py"
)
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q \
    "${ROOT}/tests/sktime_campaign/test_registry_transaction.py" \
    "${ROOT}/tests/sktime_campaign/test_registry_artifacts.py" \
    | tee "${RUN_DIR}/focused-pytest.log"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/build_sktime_p8_request.py" \
    --p7-dir "${SKTIME_P8_P7_EVIDENCE_DIR}" \
    --registry-state "${SKTIME_P8_REGISTRY_STATE}" \
    --output "${RESOLVED_REQUEST}" \
    --evidence-output-dir "${EVIDENCE_DIR}" \
    --run-id "${RUN_ID}" \
    --git-commit "${GIT_COMMIT}" \
    --code-sha256 "${CODE_SHA256}" \
    --config-sha256 "${CONFIG_SHA256}" \
    --requested-at-utc "${SKTIME_P8_REQUESTED_AT_UTC}" \
    --transaction-nonce "${SKTIME_P8_TRANSACTION_NONCE}" \
    | tee "${LOG_DIR}/request-builder.log"

COMMITTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_p8_transaction.py" \
    --request "${RESOLVED_REQUEST}" \
    --committed-at-utc "${COMMITTED_AT_UTC}" \
    | tee "${LOG_DIR}/provider.log"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p8_run.py" \
    --request "${RESOLVED_REQUEST}" \
    --output "${EVIDENCE_DIR}" \
    | tee "${LOG_DIR}/verification.log"

(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

cat "${EVIDENCE_DIR}/TRANSACTION_RECEIPT.json"
echo "SKTIME_P8_STATUS=REGISTERED_NOT_DEPLOYED"
