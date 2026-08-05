#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_DIR="${ROOT}/environments/merlion-core-py311"
RUN_ID="${RUN_ID:-merlion-bootstrap-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${OUT:-${ROOT}/artifacts/merlion-bootstrap/${RUN_ID}}"
LOG="${OUT}/bootstrap.log"
EXIT_FILE="${OUT}/exit_code"
mkdir -p "${OUT}"

finish() {
  code=$?
  printf '%s\n' "${code}" > "${EXIT_FILE}"
  printf 'BOOTSTRAP_EXIT_CODE=%s\n' "${code}"
}
trap finish EXIT

{
  echo "RUN_ID=${RUN_ID}"
  echo "ROOT=${ROOT}"
  echo "ENV_DIR=${ENV_DIR}"
  command -v uv
  uv --version
  uv python find 3.11
  uv lock --project "${ENV_DIR}" --python 3.11
  test -s "${ENV_DIR}/uv.lock"
  sha256sum "${ENV_DIR}/pyproject.toml" "${ENV_DIR}/uv.lock" \
    | tee "${OUT}/dependency-sha256.txt"
  uv sync --project "${ENV_DIR}" --frozen --python 3.11
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
  echo "BOOTSTRAP_STATUS=PASS"
  echo "NEXT_ACTION=review and commit environments/merlion-core-py311/uv.lock"
} 2>&1 | tee "${LOG}"

if [[ -t 0 && "${WAIT_FOR_ENTER:-1}" == "1" ]]; then
  read -r -p "Press Enter to close..." _
fi
