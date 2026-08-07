#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-gluonts-p7-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${1:-${ROOT}/artifacts/gluonts-p7/${RUN_ID}}"
COMPAT_OUT="${OUT}/compat"
LATEST_OUT="${OUT}/latest"
AUDIT_OUT="${OUT}/audit"
GPU_LOG="${OUT}/gpu_process_monitor.log"

mkdir -p "${COMPAT_OUT}" "${LATEST_OUT}" "${AUDIT_OUT}"
printf '%s\n' "${RUN_ID}" > "${OUT}/RUN_ID"

monitor_gpu() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    printf '%s\n' "NVIDIA_SMI=UNAVAILABLE" >> "${GPU_LOG}"
    return
  fi
  while true; do
    date -u +'%Y-%m-%dT%H:%M:%SZ'
    nvidia-smi \
      --query-compute-apps=pid,process_name,used_gpu_memory \
      --format=csv,noheader,nounits \
      || true
    sleep 2
  done >> "${GPU_LOG}" 2>&1
}

monitor_gpu &
GPU_MONITOR_PID=$!
cleanup() {
  kill "${GPU_MONITOR_PID}" 2>/dev/null || true
  wait "${GPU_MONITOR_PID}" 2>/dev/null || true
}
trap cleanup EXIT

set +e
RUN_ID="${RUN_ID}-compat" \
bash "${ROOT}/environments/gluonts-compat/p6_bootstrap_and_certify.sh" \
  "${COMPAT_OUT}" \
  > "${OUT}/compat_bootstrap.stdout.log" \
  2> "${OUT}/compat_bootstrap.stderr.log"
COMPAT_RC=$?
printf '%s\n' "${COMPAT_RC}" > "${OUT}/compat_bootstrap.rc"

RUN_ID="${RUN_ID}-latest" \
bash "${ROOT}/environments/gluonts-latest/p6_bootstrap_and_certify.sh" \
  "${LATEST_OUT}" \
  > "${OUT}/latest_bootstrap.stdout.log" \
  2> "${OUT}/latest_bootstrap.stderr.log"
LATEST_RC=$?
printf '%s\n' "${LATEST_RC}" > "${OUT}/latest_bootstrap.rc"
set -e

cleanup
trap - EXIT

if python3 -c 'import pydantic' >/dev/null 2>&1; then
  AUDIT_PYTHON=(python3)
elif [[ -x "${ROOT}/environments/gluonts-compat/.venv/bin/python" ]]; then
  AUDIT_PYTHON=("${ROOT}/environments/gluonts-compat/.venv/bin/python")
elif [[ -x "${ROOT}/environments/gluonts-latest/.venv/bin/python" ]]; then
  AUDIT_PYTHON=("${ROOT}/environments/gluonts-latest/.venv/bin/python")
else
  echo "P7_BLOCKED: no Python interpreter with Pydantic is available" >&2
  exit 3
fi

set +e
PYTHONPATH="${ROOT}/src" \
"${AUDIT_PYTHON[@]}" -m loto.adapters.gluonts.p7_cli \
  --run-id "${RUN_ID}" \
  --repo-root "${ROOT}" \
  --compat-artifact-root "${COMPAT_OUT}" \
  --latest-artifact-root "${LATEST_OUT}" \
  --compat-return-code "${COMPAT_RC}" \
  --latest-return-code "${LATEST_RC}" \
  --output-dir "${AUDIT_OUT}" \
  > "${OUT}/p7_audit.stdout.log" \
  2> "${OUT}/p7_audit.stderr.log"
AUDIT_RC=$?
set -e
printf '%s\n' "${AUDIT_RC}" > "${OUT}/p7_audit.rc"

(
  cd "${OUT}"
  find . -type f ! -name P7_EXECUTION_SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 sha256sum \
    > P7_EXECUTION_SHA256SUMS
)

cat "${OUT}/p7_audit.stdout.log"
echo "P7_RUN_ID=${RUN_ID}"
echo "P7_ARTIFACT_DIR=${OUT}"
echo "P7_COMPAT_RC=${COMPAT_RC}"
echo "P7_LATEST_RC=${LATEST_RC}"
echo "P7_AUDIT_RC=${AUDIT_RC}"
exit "${AUDIT_RC}"
