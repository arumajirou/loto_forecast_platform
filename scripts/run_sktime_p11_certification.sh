#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
CEREMONY_DIR="${SKTIME_P11_CEREMONY_DIR:?missing SKTIME_P11_CEREMONY_DIR}"
REQUEST_BASE="${CEREMONY_DIR}/intent/request-base.json"
REQUEST="${CEREMONY_DIR}/resolved-request.json"
EVIDENCE_DIR="${CEREMONY_DIR}/primary-promotion-authorization"
LOG_DIR="${CEREMONY_DIR}/logs"
EXIT_CODE_FILE="${CEREMONY_DIR}/exit_code.txt"
mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P11_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P11_CEREMONY_DIR=%s\n' "${CEREMONY_DIR}"
    if [[ "${SKTIME_NO_PAUSE:-0}" != "1" && -t 0 ]]; then
        read -r -p "Press Enter to close..." _
    fi
    exit "${rc}"
}
trap finish EXIT
exec > >(tee -a "${LOG_DIR}/certification.log") 2>&1

cd "${ROOT}"
test -f "${REQUEST_BASE}"
if [[ -z "${SKTIME_P11_APPROVAL_FILES:-}" ]]; then
    echo "BLOCKED: missing SKTIME_P11_APPROVAL_FILES"
    exit 2
fi
IFS=':' read -r -a approval_files <<< "${SKTIME_P11_APPROVAL_FILES}"
if [[ "${#approval_files[@]}" -ne 3 ]]; then
    echo "BLOCKED: exactly three approval files are required"
    exit 2
fi
approval_args=()
for path in "${approval_files[@]}"; do
    test -f "${path}"
    approval_args+=(--approval "${path}")
done

uv lock --project "${ENV_DIR}"
uv sync --project "${ENV_DIR}" --group dev --frozen
export PYTHONPATH="${ROOT}/src:${ROOT}/tests/sktime_campaign"

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign/primary_promotion_authorization.py"
    "${ROOT}/src/loto/sktime_campaign/primary_promotion_artifacts.py"
    "${ROOT}/scripts/prepare_sktime_p11_intent.py"
    "${ROOT}/scripts/prepare_sktime_p11_approval.py"
    "${ROOT}/scripts/finalize_sktime_p11_approval.py"
    "${ROOT}/scripts/build_sktime_p11_request.py"
    "${ROOT}/scripts/run_sktime_p11_authorization.py"
    "${ROOT}/scripts/verify_sktime_p11_run.py"
    "${ROOT}/tests/sktime_campaign/test_primary_promotion_authorization.py"
    "${ROOT}/tests/sktime_campaign/test_primary_promotion_artifacts.py"
)
uv run --project "${ENV_DIR}" --group dev \
    ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q \
    tests/sktime_campaign/test_primary_promotion_authorization.py \
    tests/sktime_campaign/test_primary_promotion_artifacts.py

uv run --project "${ENV_DIR}" --group dev \
    python scripts/build_sktime_p11_request.py \
    --request-base "${REQUEST_BASE}" \
    "${approval_args[@]}" \
    --output "${REQUEST}"

ISSUED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
uv run --project "${ENV_DIR}" --group dev \
    python scripts/run_sktime_p11_authorization.py \
    --request "${REQUEST}" \
    --issued-at-utc "${ISSUED_AT_UTC}"

uv run --project "${ENV_DIR}" --group dev \
    python scripts/verify_sktime_p11_run.py \
    --request "${REQUEST}" \
    --evidence-dir "${EVIDENCE_DIR}"

(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

cat "${EVIDENCE_DIR}/response.json"
cat "${EVIDENCE_DIR}/PRIMARY_PROMOTION_AUTHORIZATION.json"
