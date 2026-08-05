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
PACKAGING_FAILURE="${OUT}/EVIDENCE_PACKAGING_FAILURE.json"
PACKAGING_FAILURE_EXIT=70

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
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "schema_version": "merlion-bootstrap-failure-v1",
    "status": "BLOCKED",
    "run_id": sys.argv[2],
    "stage": sys.argv[3],
    "exit_code": int(sys.argv[4]),
}
path.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(
    mode="w",
    encoding="utf-8",
    dir=path.parent,
    prefix=f".{path.name}.",
    suffix=".tmp",
    delete=False,
) as stream:
    json.dump(payload, stream, indent=2, sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
    temporary = Path(stream.name)
temporary.replace(path)
PY
}

write_packaging_failure() {
  local bootstrap_code="$1"
  local packaging_code="$2"
  python3 - \
    "${PACKAGING_FAILURE}" \
    "${RUN_ID}" \
    "${bootstrap_code}" \
    "${packaging_code}" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "schema_version": "merlion-evidence-packaging-failure-v1",
    "status": "BLOCKED",
    "run_id": sys.argv[2],
    "bootstrap_exit_code": int(sys.argv[3]),
    "packaging_exit_code": int(sys.argv[4]),
}
path.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(
    mode="w",
    encoding="utf-8",
    dir=path.parent,
    prefix=f".{path.name}.",
    suffix=".tmp",
    delete=False,
) as stream:
    json.dump(payload, stream, indent=2, sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
    temporary = Path(stream.name)
temporary.replace(path)
PY
}

package_evidence() {
  local bootstrap_code="$1"
  local packaging_code=0
  python3 "${ROOT}/scripts/package_merlion_bootstrap_evidence.py" \
    --run-dir "${OUT}" \
    --environment-dir "${ENV_DIR}" \
    --run-id "${RUN_ID}" \
    --output "${ZIP_PATH}" \
    --verification "${VERIFY_PATH}" \
    || packaging_code=$?
  if [[ "${packaging_code}" -ne 0 ]]; then
    write_packaging_failure "${bootstrap_code}" "${packaging_code}"
    echo "EVIDENCE_PACKAGING_STATUS=BLOCKED"
    echo "EVIDENCE_PACKAGING_EXIT_CODE=${packaging_code}"
    echo "EVIDENCE_PACKAGING_FAILURE=${PACKAGING_FAILURE}"
    return "${PACKAGING_FAILURE_EXIT}"
  fi
  return 0
}

python3 "${ROOT}/scripts/run_merlion_core_preflight.py" \
  --root "${ROOT}" \
  --output "${OUT}/PREFLIGHT.json" \
  || true

set +e
python3 "${ROOT}/scripts/record_merlion_git_provenance.py" \
  --root "${ROOT}" \
  --output "${OUT}/GIT_PROVENANCE.json"
GIT_CODE=$?
set -e
if [[ "${GIT_CODE}" -ne 0 ]]; then
  write_failure "git_provenance" "${GIT_CODE}"
  PACKAGE_CODE=0
  package_evidence "${GIT_CODE}" || PACKAGE_CODE=$?
  if [[ "${PACKAGE_CODE}" -ne 0 ]]; then
    exit "${PACKAGE_CODE}"
  fi
  printf 'BOOTSTRAP_RESUME_EXIT_CODE=%s\n' "${GIT_CODE}"
  printf 'BOOTSTRAP_EVIDENCE_ZIP=%s\n' "${ZIP_PATH}"
  exit "${GIT_CODE}"
fi

set +e
python3 "${ROOT}/scripts/run_merlion_core_bootstrap_resume.py" \
  --root "${ROOT}" \
  --preflight "${OUT}/PREFLIGHT.json" \
  --run-id "${RUN_ID}" \
  --managed-python-dir "${MANAGED_DIR}" \
  --output "${OUT}/BOOTSTRAP_PLAN.json"
PLAN_CODE=$?
set -e

if [[ ! -f "${OUT}/BOOTSTRAP_PLAN.json" ]]; then
  write_failure "resume_plan" "${PLAN_CODE:-2}"
  PACKAGE_CODE=0
  package_evidence "${PLAN_CODE:-2}" || PACKAGE_CODE=$?
  if [[ "${PACKAGE_CODE}" -ne 0 ]]; then
    exit "${PACKAGE_CODE}"
  fi
  exit "${PLAN_CODE:-2}"
fi

set +e
python3 "${ROOT}/scripts/verify_merlion_bootstrap_lineage.py" \
  --preflight "${OUT}/PREFLIGHT.json" \
  --plan "${OUT}/BOOTSTRAP_PLAN.json"
LINEAGE_CODE=$?
set -e
if [[ "${LINEAGE_CODE}" -ne 0 ]]; then
  write_failure "preflight_plan_lineage" "${LINEAGE_CODE}"
  PACKAGE_CODE=0
  package_evidence "${LINEAGE_CODE}" || PACKAGE_CODE=$?
  if [[ "${PACKAGE_CODE}" -ne 0 ]]; then
    exit "${PACKAGE_CODE}"
  fi
  exit "${LINEAGE_CODE}"
fi

PREFLIGHT_REPORT_SHA256="$(
  python3 - "${OUT}/PREFLIGHT.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["report_sha256"])
PY
)"
PREFLIGHT_FILE_SHA_BEFORE="$(sha256sum "${OUT}/PREFLIGHT.json" | awk '{print $1}')"

PLAN_STATUS="$(
  python3 - "${OUT}/BOOTSTRAP_PLAN.json" <<'PY'
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
  MERLION_PYTHON="$(
    python3 - "${OUT}/PREFLIGHT.json" <<'PY'
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
  RUN_ID="${RUN_ID}" \
  OUT="${OUT}" \
  WAIT_FOR_ENTER=0 \
  MERLION_PREFLIGHT_MODE=REUSE \
  MERLION_PREFLIGHT_REPORT_SHA256="${PREFLIGHT_REPORT_SHA256}" \
    bash "${ROOT}/scripts/bootstrap_merlion_core_env.sh"
  BOOTSTRAP_CODE=$?
  set -e
fi

PREFLIGHT_FILE_SHA_AFTER="$(sha256sum "${OUT}/PREFLIGHT.json" | awk '{print $1}')"
if [[ "${PREFLIGHT_FILE_SHA_AFTER}" != "${PREFLIGHT_FILE_SHA_BEFORE}" ]]; then
  write_failure "preflight_lineage_mutated" 73
  BOOTSTRAP_CODE=73
fi

PACKAGE_CODE=0
package_evidence "${BOOTSTRAP_CODE}" || PACKAGE_CODE=$?
if [[ "${PACKAGE_CODE}" -ne 0 ]]; then
  exit "${PACKAGE_CODE}"
fi

printf 'BOOTSTRAP_RESUME_EXIT_CODE=%s\n' "${BOOTSTRAP_CODE}"
printf 'BOOTSTRAP_EVIDENCE_ZIP=%s\n' "${ZIP_PATH}"
printf 'BOOTSTRAP_EVIDENCE_SHA256_FILE=%s\n' "${ZIP_PATH}.sha256"
exit "${BOOTSTRAP_CODE}"
