#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_DIR="${ROOT}/environments/merlion-core-py311"
LOCK="${ENV_DIR}/uv.lock"
RUN_ID="${RUN_ID:-merlion-core-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${OUT:-${ROOT}/artifacts/merlion-core-runtime/${RUN_ID}}"
CONSOLE_LOG="${OUT}.console.log"
EXIT_FILE="${OUT}.exit_code"
EXPECTED_GIT_SHA="${EXPECTED_GIT_SHA:-$(git -C "${ROOT}" rev-parse HEAD)}"
mkdir -p "$(dirname "${OUT}")"

finish() {
  code=$?
  printf '%s\n' "${code}" > "${EXIT_FILE}"
  printf 'CERTIFICATION_EXIT_CODE=%s\n' "${code}"
}
trap finish EXIT

{
  test -f "${LOCK}"
  git -C "${ROOT}" diff --quiet
  git -C "${ROOT}" diff --cached --quiet
  test -z "$(git -C "${ROOT}" ls-files --others --exclude-standard)"
  ACTUAL_GIT_SHA="$(git -C "${ROOT}" rev-parse HEAD)"
  test "${ACTUAL_GIT_SHA}" = "${EXPECTED_GIT_SHA}"
  git -C "${ROOT}" ls-files --error-unmatch \
    "environments/merlion-core-py311/uv.lock" >/dev/null

  LOCK_SHA256="$(sha256sum "${LOCK}" | awk '{print $1}')"
  uv sync --project "${ENV_DIR}" --frozen --python 3.11

  PROVIDER_COMMAND_JSON="$(python - "${ROOT}" "${ENV_DIR}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
env_dir = Path(sys.argv[2])
print(json.dumps([
    "uv", "run", "--project", str(env_dir), "--frozen", "python",
    str(root / "scripts" / "run_merlion_provider.py"),
]))
PY
)"

  export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
  uv run --project "${ROOT}" --frozen python \
    "${ROOT}/scripts/run_merlion_core_certification.py" run \
    --provider-command-json "${PROVIDER_COMMAND_JSON}" \
    --output "${OUT}" \
    --expected-git-sha "${EXPECTED_GIT_SHA}" \
    --lock-sha256 "${LOCK_SHA256}" \
    --timeout-seconds "${MERLION_MODEL_TIMEOUT_SECONDS:-300}"

  uv run --project "${ROOT}" --frozen python \
    "${ROOT}/scripts/run_merlion_core_certification.py" verify \
    --run "${OUT}"
  echo "MERLION_CORE_CERTIFICATION=PASS"
  echo "RUN_DIR=${OUT}"
} 2>&1 | tee "${CONSOLE_LOG}"

if [[ -t 0 && "${WAIT_FOR_ENTER:-1}" == "1" ]]; then
  read -r -p "Press Enter to close..." _
fi
