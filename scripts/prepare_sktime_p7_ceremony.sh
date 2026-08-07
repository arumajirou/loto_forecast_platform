#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
POLICY_CONFIG="${SKTIME_P7_POLICY_CONFIG:-${ROOT}/configs/sktime_campaign/approval_policy.json}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
CEREMONY_DIR="${SKTIME_P7_CEREMONY_DIR:-${ROOT}/artifacts/sktime-p7-ceremony/${RUN_ID}}"
INTENT_DIR="${CEREMONY_DIR}/intent"
FUTURE_EVIDENCE_DIR="${ROOT}/artifacts/sktime-p7/${RUN_ID}/manual-approval-authorization"

required_vars=(
    SKTIME_P7_P6_EVIDENCE_DIR
    SKTIME_P7_SUBJECT_CONFIG
    SKTIME_P7_ALLOWED_SIGNERS_FILE
)
for name in "${required_vars[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        echo "BLOCKED: required environment variable is missing: ${name}"
        exit 2
    fi
done

command -v git
command -v uv
command -v sha256sum
command -v openssl

test -f "${POLICY_CONFIG}"
test -f "${SKTIME_P7_SUBJECT_CONFIG}"
test -f "${SKTIME_P7_ALLOWED_SIGNERS_FILE}"
test -d "${SKTIME_P7_P6_EVIDENCE_DIR}"
test ! -e "${CEREMONY_DIR}"
mkdir -p "${CEREMONY_DIR}"

REQUESTED_AT_UTC="${SKTIME_P7_REQUESTED_AT_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
EXPIRES_AT_UTC="${SKTIME_P7_EXPIRES_AT_UTC:-$(
    python - "${REQUESTED_AT_UTC}" <<'PY'
from datetime import datetime, timedelta
import sys

value = datetime.strptime(sys.argv[1], "%Y-%m-%dT%H:%M:%SZ")
print((value + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
PY
)}"
AUTHORIZATION_NONCE="${SKTIME_P7_AUTHORIZATION_NONCE:-$(openssl rand -hex 32)}"
GIT_COMMIT="$(git -C "${ROOT}" rev-parse HEAD)"

CONFIG_SHA_INPUT="${CEREMONY_DIR}/CONFIG_SHA256_INPUT"
sha256sum \
    "${POLICY_CONFIG}" \
    "${SKTIME_P7_SUBJECT_CONFIG}" \
    "${SKTIME_P7_ALLOWED_SIGNERS_FILE}" \
    | tee "${CONFIG_SHA_INPUT}"
CONFIG_SHA256="$(sha256sum "${CONFIG_SHA_INPUT}" | awk '{print $1}')"

CODE_SHA_INPUT="${CEREMONY_DIR}/CODE_SHA256_INPUT"
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

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/prepare_sktime_p7_intent.py" \
    --p6-dir "${SKTIME_P7_P6_EVIDENCE_DIR}" \
    --policy-config "${POLICY_CONFIG}" \
    --subject-config "${SKTIME_P7_SUBJECT_CONFIG}" \
    --allowed-signers "${SKTIME_P7_ALLOWED_SIGNERS_FILE}" \
    --output-dir "${INTENT_DIR}" \
    --evidence-output-dir "${FUTURE_EVIDENCE_DIR}" \
    --run-id "${RUN_ID}" \
    --git-commit "${GIT_COMMIT}" \
    --code-sha256 "${CODE_SHA256}" \
    --config-sha256 "${CONFIG_SHA256}" \
    --requested-at-utc "${REQUESTED_AT_UTC}" \
    --expires-at-utc "${EXPIRES_AT_UTC}" \
    --authorization-nonce "${AUTHORIZATION_NONCE}"

ENV_FILE="${CEREMONY_DIR}/ceremony.env"
cat > "${ENV_FILE}" <<EOF
export SKTIME_RUN_ID='${RUN_ID}'
export SKTIME_P7_P6_EVIDENCE_DIR='${SKTIME_P7_P6_EVIDENCE_DIR}'
export SKTIME_P7_SUBJECT_CONFIG='${SKTIME_P7_SUBJECT_CONFIG}'
export SKTIME_P7_ALLOWED_SIGNERS_FILE='${SKTIME_P7_ALLOWED_SIGNERS_FILE}'
export SKTIME_P7_POLICY_CONFIG='${POLICY_CONFIG}'
export SKTIME_P7_REQUESTED_AT_UTC='${REQUESTED_AT_UTC}'
export SKTIME_P7_EXPIRES_AT_UTC='${EXPIRES_AT_UTC}'
export SKTIME_P7_AUTHORIZATION_NONCE='${AUTHORIZATION_NONCE}'
EOF

printf 'SKTIME_P7_CEREMONY_DIR=%s\n' "${CEREMONY_DIR}"
printf 'SKTIME_P7_INTENT=%s\n' "${INTENT_DIR}/APPROVAL_INTENT.json"
printf 'SKTIME_P7_ENV_FILE=%s\n' "${ENV_FILE}"
printf 'SKTIME_P7_EXPIRES_AT_UTC=%s\n' "${EXPIRES_AT_UTC}"
