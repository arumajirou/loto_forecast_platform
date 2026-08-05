#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_DIR="${ROOT}/environments/merlion-core-py311"
RUN_ID="${RUN_ID:-merlion-bootstrap-resume-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${OUT:-${ROOT}/artifacts/merlion-bootstrap/${RUN_ID}}"
MANAGED_DIR="${MANAGED_DIR:-${ROOT}/artifacts/merlion-managed-python/cpython-3.11}"
PACKAGE_DIR="${PACKAGE_DIR:-${ROOT}/artifacts/merlion-bootstrap-packages}"
ZIP_PATH="${PACKAGE_DIR}/${RUN_ID}.zip"
VERIFY_PATH="${PACKAGE_DIR}/${RUN_ID}.verification.json"
if [[ -e "${OUT}" || -e "${ZIP_PATH}" || -e "${ZIP_PATH}.sha256" ]]; then
  echo "BLOCKED: Run ID outputs already exist: ${RUN_ID}"
  exit 2
fi
mkdir -p "${OUT}" "${PACKAGE_DIR}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

write_failure() {
  local stage="$1"
  local code="$2"
  printf '%s\n' "${code}" > "${OUT}/exit_code"
  python3 - "${OUT}/BOOTSTRAP_FAILURE.json" "${RUN_ID}" "${stage}" "${code}" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": "merlion-bootstrap-failure-v1",
            "status": "BLOCKED",
            "run_id": sys.argv[2],
            "stage": sys.argv[3],
            "exit_code": int(sys.argv[4]),
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
}

python3 "${ROOT}/scripts/run_merlion_core_preflight.py" \
  --root "${ROOT}" \
  --output "${OUT}/PREFLIGHT.json" \
  || true

set +e
python3 "${ROOT}/scripts/run_merlion_core_bootstrap_resume.py" \
  --root "${ROOT}" \
  --preflight "${OUT}/PREFLIGHT.json" \
  --run-id "${RUN_ID}" \
  --managed-python-dir "${MANAGED_DIR}" \
  --output "${OUT}/BOOTSTRAP_PLAN.json"
PLAN_CODE=$?
set -e

PLAN_STATUS="$(python3 - "${OUT}/BOOTSTRAP_PLAN.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["status"])
PY
)"

BOOTSTRAP_CODE="${PLAN_CODE}"
MERLION_PYTHON=""
if [[ "${PLAN_STATUS}" == "READY_TO_PROVISION_PYTHON" ]]; then
  export UV_PYTHON_INSTALL_DIR="${MANAGED_DIR}"
  set +e
  uv python install 3.11 \
    --install-dir "${MANAGED_DIR}" \
    --no-bin \
    2>&1 | tee "${OUT}/PYTHON_PROVISION.log"
  PROVISION_CODE=${PIPESTATUS[0]}
  set -e
  if [[ "${PROVISION_CODE}" -eq 0 ]]; then
    MERLION_PYTHON="$(uv python find --managed-python 3.11)"
  else
    write_failure "python_provision" "${PROVISION_CODE}"
    BOOTSTRAP_CODE="${PROVISION_CODE}"
  fi
elif [[ "${PLAN_STATUS}" == "READY_TO_BOOTSTRAP" ]]; then
  MERLION_PYTHON="$(python3 - "${OUT}/PREFLIGHT.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["python_311"]["path"])
PY
)"
else
  write_failure "resume_plan" 2
  BOOTSTRAP_CODE=2
fi

if [[ -n "${MERLION_PYTHON}" ]]; then
  printf '%s\n' "${MERLION_PYTHON}" > "${OUT}/PYTHON_PATH.txt"
  export MERLION_PYTHON
  set +e
  RUN_ID="${RUN_ID}" OUT="${OUT}" WAIT_FOR_ENTER=0 \
    bash "${ROOT}/scripts/bootstrap_merlion_core_env.sh"
  BOOTSTRAP_CODE=$?
  set -e
fi

python3 "${ROOT}/scripts/package_merlion_bootstrap_evidence.py" \
  --run-dir "${OUT}" \
  --environment-dir "${ENV_DIR}" \
  --run-id "${RUN_ID}" \
  --output "${ZIP_PATH}" \
  --verification "${VERIFY_PATH}"

printf 'BOOTSTRAP_RESUME_EXIT_CODE=%s\n' "${BOOTSTRAP_CODE}"
printf 'BOOTSTRAP_EVIDENCE_ZIP=%s\n' "${ZIP_PATH}"
printf 'BOOTSTRAP_EVIDENCE_SHA256_FILE=%s\n' "${ZIP_PATH}.sha256"
exit "${BOOTSTRAP_CODE}"
