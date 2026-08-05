#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
POLICY_CONFIG="${SKTIME_P7_POLICY_CONFIG:-${ROOT}/configs/sktime_campaign/approval_policy.json}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p7/${RUN_ID}}"
EVIDENCE_DIR="${RUN_DIR}/manual-approval-authorization"
LOG_DIR="${RUN_DIR}/logs"
MAIN_LOG="${LOG_DIR}/certification.log"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"
RESOLVED_REQUEST="${RUN_DIR}/resolved-request.json"
ISSUED_AT_FILE="${RUN_DIR}/issued-at-utc.txt"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P7_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P7_RUN_DIR=%s\n' "${RUN_DIR}"
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
command -v ssh-keygen

test -f "${POLICY_CONFIG}"

required_vars=(
    SKTIME_P7_P6_EVIDENCE_DIR
    SKTIME_P7_SUBJECT_CONFIG
    SKTIME_P7_ALLOWED_SIGNERS_FILE
    SKTIME_P7_APPROVAL_FILES
    SKTIME_P7_REQUESTED_AT_UTC
    SKTIME_P7_EXPIRES_AT_UTC
    SKTIME_P7_AUTHORIZATION_NONCE
)
for name in "${required_vars[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        echo "BLOCKED: required environment variable is missing: ${name}"
        exit 2
    fi
done

IFS=':' read -r -a APPROVAL_FILES <<< "${SKTIME_P7_APPROVAL_FILES}"
if [[ "${#APPROVAL_FILES[@]}" -ne 2 ]]; then
    echo "BLOCKED: exactly two approval files are required"
    exit 2
fi

for path in \
    "${SKTIME_P7_SUBJECT_CONFIG}" \
    "${SKTIME_P7_ALLOWED_SIGNERS_FILE}" \
    "${APPROVAL_FILES[@]}"; do
    test -f "${path}"
done

test -d "${SKTIME_P7_P6_EVIDENCE_DIR}"
(
    cd "${SKTIME_P7_P6_EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

GIT_COMMIT="$(git rev-parse HEAD)"
CONFIG_SHA_INPUT="${RUN_DIR}/CONFIG_SHA256_INPUT"
sha256sum \
    "${POLICY_CONFIG}" \
    "${SKTIME_P7_SUBJECT_CONFIG}" \
    "${SKTIME_P7_ALLOWED_SIGNERS_FILE}" \
    | tee "${CONFIG_SHA_INPUT}"
CONFIG_SHA256="$(sha256sum "${CONFIG_SHA_INPUT}" | awk '{print $1}')"

CODE_SHA_INPUT="${RUN_DIR}/CODE_SHA256_INPUT"
(
    cd "${ROOT}"
    sha256sum \
        src/loto/sktime_campaign/approval_authorization.py \
        src/loto/sktime_campaign/approval_artifacts.py \
        scripts/build_sktime_p7_request.py \
        scripts/run_sktime_p7_authorization.py \
        scripts/verify_sktime_p7_run.py
) | tee "${CODE_SHA_INPUT}"
CODE_SHA256="$(sha256sum "${CODE_SHA_INPUT}" | awk '{print $1}')"

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'git_commit=%s\n' "${GIT_COMMIT}"
    printf 'config_sha256=%s\n' "${CONFIG_SHA256}"
    printf 'code_sha256=%s\n' "${CODE_SHA256}"
    printf 'approval_count=%s\n' "${#APPROVAL_FILES[@]}"
    printf 'uv_version=%s\n' "$(uv --version)"
} | tee "${RUN_DIR}/RUN_METADATA.txt"

uv lock --project "${ENV_DIR}"
test -s "${ENV_DIR}/uv.lock"
sha256sum "${ENV_DIR}/uv.lock" | tee "${RUN_DIR}/UV_LOCK_SHA256"
uv sync --project "${ENV_DIR}" --group dev --frozen

export PYTHONPATH="${ROOT}/src:${ROOT}/tests/sktime_campaign"
CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign/approval_authorization.py"
    "${ROOT}/src/loto/sktime_campaign/approval_artifacts.py"
    "${ROOT}/scripts/build_sktime_p7_request.py"
    "${ROOT}/scripts/run_sktime_p7_authorization.py"
    "${ROOT}/scripts/verify_sktime_p7_run.py"
    "${ROOT}/tests/sktime_campaign/test_approval_authorization.py"
    "${ROOT}/tests/sktime_campaign/test_approval_artifacts.py"
)
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q \
    "${ROOT}/tests/sktime_campaign/test_approval_authorization.py" \
    "${ROOT}/tests/sktime_campaign/test_approval_artifacts.py" \
    | tee "${RUN_DIR}/focused-pytest.log"

BUILD_ARGS=(
    --p6-dir "${SKTIME_P7_P6_EVIDENCE_DIR}"
    --policy-config "${POLICY_CONFIG}"
    --subject-config "${SKTIME_P7_SUBJECT_CONFIG}"
    --allowed-signers "${SKTIME_P7_ALLOWED_SIGNERS_FILE}"
    --output "${RESOLVED_REQUEST}"
    --evidence-output-dir "${EVIDENCE_DIR}"
    --run-id "${RUN_ID}"
    --git-commit "${GIT_COMMIT}"
    --code-sha256 "${CODE_SHA256}"
    --config-sha256 "${CONFIG_SHA256}"
    --requested-at-utc "${SKTIME_P7_REQUESTED_AT_UTC}"
    --expires-at-utc "${SKTIME_P7_EXPIRES_AT_UTC}"
    --authorization-nonce "${SKTIME_P7_AUTHORIZATION_NONCE}"
)
for path in "${APPROVAL_FILES[@]}"; do
    BUILD_ARGS+=(--approval "${path}")
done

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/build_sktime_p7_request.py" \
    "${BUILD_ARGS[@]}" \
    | tee "${LOG_DIR}/request-builder.log"

ISSUED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '%s\n' "${ISSUED_AT_UTC}" > "${ISSUED_AT_FILE}"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_p7_authorization.py" \
    --request "${RESOLVED_REQUEST}" \
    --allowed-signers "${SKTIME_P7_ALLOWED_SIGNERS_FILE}" \
    --issued-at-utc "${ISSUED_AT_UTC}" \
    | tee "${LOG_DIR}/provider.log"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p7_run.py" \
    --request "${RESOLVED_REQUEST}" \
    --output "${EVIDENCE_DIR}" \
    --allowed-signers "${SKTIME_P7_ALLOWED_SIGNERS_FILE}" \
    --issued-at-utc "${ISSUED_AT_UTC}" \
    | tee "${LOG_DIR}/verification.log"

(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

cat "${EVIDENCE_DIR}/REGISTRY_AUTHORIZATION.json"
echo "SKTIME_P7_STATUS=AUTHORIZED_NOT_REGISTERED"
