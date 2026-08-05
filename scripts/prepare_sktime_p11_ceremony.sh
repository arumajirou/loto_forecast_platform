#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
DEFAULT_POLICY="${ROOT}/configs/sktime_campaign/primary_promotion_authorization_policy.json"
POLICY="${SKTIME_P11_POLICY_CONFIG:-${DEFAULT_POLICY}}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
DEFAULT_CEREMONY_DIR="${ROOT}/artifacts/sktime-p11-ceremony/${RUN_ID}"
CEREMONY_DIR="${SKTIME_P11_CEREMONY_DIR:-${DEFAULT_CEREMONY_DIR}}"
INTENT_DIR="${CEREMONY_DIR}/intent"
REQUESTED_AT_UTC="${SKTIME_P11_REQUESTED_AT_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
DEFAULT_EXPIRES_AT_UTC="$(
    date -u -d "${REQUESTED_AT_UTC} + 30 minutes" +%Y-%m-%dT%H:%M:%SZ
)"
EXPIRES_AT_UTC="${SKTIME_P11_EXPIRES_AT_UTC:-${DEFAULT_EXPIRES_AT_UTC}}"
DEFAULT_AUTHORIZATION_NONCE="$(openssl rand -hex 32)"
AUTHORIZATION_NONCE="${SKTIME_P11_AUTHORIZATION_NONCE:-${DEFAULT_AUTHORIZATION_NONCE}}"

required=(
    SKTIME_P11_P10_EVIDENCE_DIR
    SKTIME_P11_DEPLOYMENT_STATE
    SKTIME_P11_ALLOWED_SIGNERS_FILE
)
for name in "${required[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        echo "BLOCKED: missing ${name}"
        exit 2
    fi
done

cd "${ROOT}"
test -d "${SKTIME_P11_P10_EVIDENCE_DIR}"
test -f "${SKTIME_P11_DEPLOYMENT_STATE}"
test -f "${SKTIME_P11_ALLOWED_SIGNERS_FILE}"
test -f "${POLICY}"

GIT_COMMIT="$(git rev-parse HEAD)"
CODE_SHA256="$(
    sha256sum \
        src/loto/sktime_campaign/primary_promotion_authorization.py \
        src/loto/sktime_campaign/primary_promotion_artifacts.py \
        scripts/prepare_sktime_p11_intent.py \
        scripts/build_sktime_p11_request.py \
    | sha256sum \
    | awk '{print $1}'
)"
CONFIG_SHA256="$(
    sha256sum "${POLICY}" "${SKTIME_P11_ALLOWED_SIGNERS_FILE}" \
    | sha256sum \
    | awk '{print $1}'
)"

uv run --project "${ENV_DIR}" --group dev \
    python scripts/prepare_sktime_p11_intent.py \
    --p10-dir "${SKTIME_P11_P10_EVIDENCE_DIR}" \
    --deployment-state "${SKTIME_P11_DEPLOYMENT_STATE}" \
    --policy "${POLICY}" \
    --allowed-signers-file "${SKTIME_P11_ALLOWED_SIGNERS_FILE}" \
    --output-dir "${INTENT_DIR}" \
    --evidence-output-dir "${CEREMONY_DIR}/primary-promotion-authorization" \
    --run-id "${RUN_ID}" \
    --git-commit "${GIT_COMMIT}" \
    --code-sha256 "${CODE_SHA256}" \
    --config-sha256 "${CONFIG_SHA256}" \
    --requested-at-utc "${REQUESTED_AT_UTC}" \
    --expires-at-utc "${EXPIRES_AT_UTC}" \
    --authorization-nonce "${AUTHORIZATION_NONCE}"

{
    printf 'export ROOT=%q\n' "${ROOT}"
    printf 'export SKTIME_P11_CEREMONY_DIR=%q\n' "${CEREMONY_DIR}"
    printf 'export SKTIME_P11_REQUESTED_AT_UTC=%q\n' "${REQUESTED_AT_UTC}"
    printf 'export SKTIME_P11_EXPIRES_AT_UTC=%q\n' "${EXPIRES_AT_UTC}"
    printf 'export SKTIME_P11_AUTHORIZATION_NONCE=%q\n' "${AUTHORIZATION_NONCE}"
} > "${CEREMONY_DIR}/ceremony.env"

echo "SKTIME_P11_CEREMONY_DIR=${CEREMONY_DIR}"
echo "SKTIME_P11_INTENT=${INTENT_DIR}/PRIMARY_PROMOTION_INTENT.json"
echo "SKTIME_P11_EXPIRES_AT_UTC=${EXPIRES_AT_UTC}"
