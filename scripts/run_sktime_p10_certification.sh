#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
POLICY="${SKTIME_P10_POLICY_CONFIG:-${ROOT}/configs/sktime_campaign/canary_evaluation_policy.json}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p10/${RUN_ID}}"
EVIDENCE_DIR="${RUN_DIR}/shadow-canary-evaluation"
LOG_DIR="${RUN_DIR}/logs"
REQUEST="${RUN_DIR}/resolved-request.json"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"
mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P10_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P10_RUN_DIR=%s\n' "${RUN_DIR}"
    if [[ "${SKTIME_NO_PAUSE:-0}" != "1" && -t 0 ]]; then
        read -r -p "Press Enter to close..." _
    fi
    exit "${rc}"
}
trap finish EXIT
exec > >(tee -a "${LOG_DIR}/certification.log") 2>&1

cd "${ROOT}"
required=(
    SKTIME_P10_P9_EVIDENCE_DIR
    SKTIME_P10_WINDOW_FILES
    SKTIME_P10_EVALUATED_AT_UTC
)
for name in "${required[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        echo "BLOCKED: missing ${name}"
        exit 2
    fi
done

test -d "${SKTIME_P10_P9_EVIDENCE_DIR}"
test -f "${POLICY}"
(
    cd "${SKTIME_P10_P9_EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)
IFS=':' read -r -a WINDOW_FILES <<< "${SKTIME_P10_WINDOW_FILES}"
if [[ "${#WINDOW_FILES[@]}" -lt 1 ]]; then
    echo "BLOCKED: no shadow evaluation windows supplied"
    exit 2
fi
for path in "${WINDOW_FILES[@]}"; do
    test -f "${path}"
done

GIT_COMMIT="$(git rev-parse HEAD)"
CONFIG_SHA256="$(
    {
        sha256sum "${POLICY}"
        sha256sum "${WINDOW_FILES[@]}"
    } | sha256sum | awk '{print $1}'
)"
CODE_SHA256="$(
    sha256sum \
        src/loto/sktime_campaign/canary_evaluation.py \
        src/loto/sktime_campaign/canary_evaluation_artifacts.py \
        scripts/build_sktime_p10_request.py \
        scripts/run_sktime_p10_evaluation.py \
        scripts/verify_sktime_p10_run.py \
    | sha256sum \
    | awk '{print $1}'
)"

uv lock --project "${ENV_DIR}"
uv sync --project "${ENV_DIR}" --group dev --frozen
export PYTHONPATH="${ROOT}/src:${ROOT}/tests/sktime_campaign"

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign/canary_evaluation.py"
    "${ROOT}/src/loto/sktime_campaign/canary_evaluation_artifacts.py"
    "${ROOT}/scripts/build_sktime_p10_request.py"
    "${ROOT}/scripts/run_sktime_p10_evaluation.py"
    "${ROOT}/scripts/verify_sktime_p10_run.py"
    "${ROOT}/tests/sktime_campaign/p10_helpers.py"
    "${ROOT}/tests/sktime_campaign/test_canary_evaluation.py"
    "${ROOT}/tests/sktime_campaign/test_canary_evaluation_artifacts.py"
)
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q \
    "${ROOT}/tests/sktime_campaign/test_canary_evaluation.py" \
    "${ROOT}/tests/sktime_campaign/test_canary_evaluation_artifacts.py" \
    | tee "${RUN_DIR}/focused-pytest.log"

BUILD_ARGS=(
    --p9-dir "${SKTIME_P10_P9_EVIDENCE_DIR}"
    --policy "${POLICY}"
    --output "${REQUEST}"
    --evidence-output-dir "${EVIDENCE_DIR}"
    --run-id "${RUN_ID}"
    --git-commit "${GIT_COMMIT}"
    --code-sha256 "${CODE_SHA256}"
    --config-sha256 "${CONFIG_SHA256}"
    --evaluated-at-utc "${SKTIME_P10_EVALUATED_AT_UTC}"
)
for path in "${WINDOW_FILES[@]}"; do
    BUILD_ARGS+=(--window "${path}")
done

uv run --project "${ENV_DIR}" --group dev \
    python scripts/build_sktime_p10_request.py "${BUILD_ARGS[@]}" \
    | tee "${LOG_DIR}/request-builder.log"
uv run --project "${ENV_DIR}" --group dev \
    python scripts/run_sktime_p10_evaluation.py --request "${REQUEST}" \
    | tee "${LOG_DIR}/provider.log"
uv run --project "${ENV_DIR}" --group dev \
    python scripts/verify_sktime_p10_run.py \
    --request "${REQUEST}" \
    --output "${EVIDENCE_DIR}" \
    | tee "${LOG_DIR}/verification.log"
(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)
cat "${EVIDENCE_DIR}/PRIMARY_PROMOTION_REVIEW_DECISION.json"
echo "SKTIME_P10_STATUS=VERIFIED_PRIMARY_UNCHANGED"
