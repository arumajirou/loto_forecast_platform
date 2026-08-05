#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_DIR="${ROOT}/environments/merlion-core-py311"
RUN_ID="${RUN_ID:-merlion-bootstrap-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${OUT:-${ROOT}/artifacts/merlion-bootstrap/${RUN_ID}}"
LOG="${OUT}/bootstrap.log"
EXIT_FILE="${OUT}/exit_code"
STAGE="initialize"
mkdir -p "${OUT}"

finish() {
  code=$?
  printf '%s\n' "${code}" > "${EXIT_FILE}"
  if [[ "${code}" -ne 0 ]]; then
    python3 - "${OUT}/BOOTSTRAP_FAILURE.json" "${RUN_ID}" "${STAGE}" "${code}" <<'PY'
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
  fi
  printf 'BOOTSTRAP_EXIT_CODE=%s\n' "${code}"
}
trap finish EXIT
exec > >(tee "${LOG}") 2>&1

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

echo "RUN_ID=${RUN_ID}"
echo "ROOT=${ROOT}"
echo "ENV_DIR=${ENV_DIR}"

STAGE="preflight"
python3 "${ROOT}/scripts/run_merlion_core_preflight.py" \
  --root "${ROOT}" \
  --output "${OUT}/PREFLIGHT.json"

STAGE="uv_identity"
command -v uv
uv --version

STAGE="python_311_resolution"
uv python find 3.11

STAGE="lock_resolution"
uv lock --project "${ENV_DIR}" --python 3.11
test -s "${ENV_DIR}/uv.lock"

STAGE="lock_audit"
python3 "${ROOT}/scripts/audit_merlion_core_lock.py" \
  --project "${ENV_DIR}" \
  --report "${OUT}/DEPENDENCY_AUDIT.json" \
  --inventory "${OUT}/DEPENDENCY_INVENTORY.csv"

STAGE="dependency_hashes"
sha256sum \
  "${ENV_DIR}/pyproject.toml" \
  "${ENV_DIR}/uv.lock" \
  "${OUT}/PREFLIGHT.json" \
  "${OUT}/DEPENDENCY_AUDIT.json" \
  "${OUT}/DEPENDENCY_INVENTORY.csv" \
  | tee "${OUT}/dependency-sha256.txt"

STAGE="frozen_sync"
uv sync --project "${ENV_DIR}" --frozen --python 3.11

STAGE="runtime_identity"
uv run --project "${ENV_DIR}" --frozen python - <<'PY'
import importlib.metadata
import numpy
import sys

assert sys.version_info[:2] == (3, 11), sys.version
assert importlib.metadata.version("salesforce-merlion") == "2.0.4"
major = int(numpy.__version__.split(".", 1)[0])
assert major < 2, numpy.__version__
print(f"python={sys.version.split()[0]}")
print(f"salesforce_merlion={importlib.metadata.version('salesforce-merlion')}")
print(f"numpy={numpy.__version__}")
PY

STAGE="complete"
echo "BOOTSTRAP_STATUS=PASS"
echo "NEXT_ACTION=review and commit environments/merlion-core-py311/uv.lock"

if [[ -t 0 && "${WAIT_FOR_ENTER:-1}" == "1" ]]; then
  read -r -p "Press Enter to close..." _
fi
