#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
POLICY="${SKTIME_P9_POLICY_CONFIG:-${ROOT}/configs/sktime_campaign/deployment_canary_policy.json}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p9/${RUN_ID}}"
EVIDENCE_DIR="${RUN_DIR}/shadow-canary-activation"
LOG_DIR="${RUN_DIR}/logs"
REQUEST="${RUN_DIR}/resolved-request.json"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"
mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P9_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P9_RUN_DIR=%s\n' "${RUN_DIR}"
    if [[ "${SKTIME_NO_PAUSE:-0}" != "1" && -t 0 ]]; then
        read -r -p "Press Enter to close..." _
    fi
    exit "${rc}"
}
trap finish EXIT
exec > >(tee -a "${LOG_DIR}/certification.log") 2>&1

cd "${ROOT}"
required=(
    SKTIME_P9_P8_EVIDENCE_DIR
    SKTIME_P9_RUNTIME_PROBE
    SKTIME_P9_DEPLOYMENT_STATE
    SKTIME_P9_DEPLOYMENT_TARGET
    SKTIME_P9_REQUESTED_AT_UTC
    SKTIME_P9_ACTIVATION_NONCE
)
for name in "${required[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        echo "BLOCKED: missing ${name}"
        exit 2
    fi
done

test -f "${POLICY}"
test -f "${SKTIME_P9_RUNTIME_PROBE}"
test -f "${SKTIME_P9_DEPLOYMENT_STATE}"
test -d "${SKTIME_P9_P8_EVIDENCE_DIR}"
(
    cd "${SKTIME_P9_P8_EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

GIT_COMMIT="$(git rev-parse HEAD)"
CONFIG_SHA256="$(
    sha256sum "${POLICY}" "${SKTIME_P9_RUNTIME_PROBE}" \
    | sha256sum \
    | awk '{print $1}'
)"
CODE_SHA256="$(
    sha256sum \
        src/loto/sktime_campaign/deployment_canary.py \
        src/loto/sktime_campaign/deployment_artifacts.py \
        scripts/build_sktime_p9_request.py \
        scripts/run_sktime_p9_canary.py \
        scripts/verify_sktime_p9_run.py \
    | sha256sum \
    | awk '{print $1}'
)"

uv lock --project "${ENV_DIR}"
uv sync --project "${ENV_DIR}" --group dev --frozen
export PYTHONPATH="${ROOT}/src"

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign/deployment_canary.py"
    "${ROOT}/src/loto/sktime_campaign/deployment_artifacts.py"
    "${ROOT}/scripts/bootstrap_sktime_p9_deployment.py"
    "${ROOT}/scripts/build_sktime_p9_request.py"
    "${ROOT}/scripts/run_sktime_p9_canary.py"
    "${ROOT}/scripts/verify_sktime_p9_run.py"
    "${ROOT}/tests/sktime_campaign/test_deployment_canary.py"
    "${ROOT}/tests/sktime_campaign/test_deployment_artifacts.py"
)
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q \
    tests/sktime_campaign/test_deployment_canary.py \
    tests/sktime_campaign/test_deployment_artifacts.py \
    | tee "${RUN_DIR}/focused-pytest.log"

uv run --project "${ENV_DIR}" --group dev \
    python scripts/build_sktime_p9_request.py \
    --p8-dir "${SKTIME_P9_P8_EVIDENCE_DIR}" \
    --runtime-probe "${SKTIME_P9_RUNTIME_PROBE}" \
    --policy "${POLICY}" \
    --deployment-state "${SKTIME_P9_DEPLOYMENT_STATE}" \
    --deployment-target "${SKTIME_P9_DEPLOYMENT_TARGET}" \
    --output "${REQUEST}" \
    --evidence-output-dir "${EVIDENCE_DIR}" \
    --run-id "${RUN_ID}" \
    --git-commit "${GIT_COMMIT}" \
    --code-sha256 "${CODE_SHA256}" \
    --config-sha256 "${CONFIG_SHA256}" \
    --requested-at-utc "${SKTIME_P9_REQUESTED_AT_UTC}" \
    --activation-nonce "${SKTIME_P9_ACTIVATION_NONCE}"

COMMITTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
uv run --project "${ENV_DIR}" --group dev \
    python scripts/run_sktime_p9_canary.py \
    --request "${REQUEST}" \
    --committed-at-utc "${COMMITTED_AT_UTC}"
uv run --project "${ENV_DIR}" --group dev \
    python scripts/verify_sktime_p9_run.py \
    --request "${REQUEST}" \
    --output "${EVIDENCE_DIR}"
(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)
cat "${EVIDENCE_DIR}/response.json"
echo "SKTIME_P9_STATUS=CANARY_ACTIVE_NOT_PRIMARY"
