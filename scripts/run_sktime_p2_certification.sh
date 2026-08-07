#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p2/${RUN_ID}}"
LOG_DIR="${RUN_DIR}/logs"
MAIN_LOG="${LOG_DIR}/certification.log"
REQUEST_FILE="$(mktemp /tmp/sktime-p2-request-XXXXXX.json)"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    rm -f "${REQUEST_FILE}"
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P2_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P2_RUN_DIR=%s\n' "${RUN_DIR}"
    if [[ "${SKTIME_NO_PAUSE:-0}" != "1" && -t 0 ]]; then
        read -r -p "Press Enter to close..." _
    fi
    exit "${rc}"
}
trap finish EXIT

exec > >(tee -a "${MAIN_LOG}") 2>&1

cd "${ROOT}"

command -v git
command -v uv
command -v sha256sum

test -f "${ENV_DIR}/pyproject.toml"
test -f "${ROOT}/configs/sktime_campaign/chronological_validation.json"
test -f "${ROOT}/scripts/run_sktime_p2_benchmark.py"
test -f "${ROOT}/scripts/verify_sktime_p2_run.py"

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'git_head=%s\n' "$(git rev-parse HEAD)"
    printf 'git_branch=%s\n' "$(git branch --show-current)"
    printf 'uv_version=%s\n' "$(uv --version)"
    printf 'run_id=%s\n' "${RUN_ID}"
} | tee "${RUN_DIR}/RUN_METADATA.txt"

uv lock --project "${ENV_DIR}"
test -s "${ENV_DIR}/uv.lock"
sha256sum "${ENV_DIR}/uv.lock" | tee "${RUN_DIR}/UV_LOCK_SHA256"
uv sync --project "${ENV_DIR}" --group dev --frozen

export PYTHONPATH="${ROOT}/src"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

python - \
    "${ROOT}/configs/sktime_campaign/chronological_validation.json" \
    "${REQUEST_FILE}" \
    "${RUN_DIR}/benchmark" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
output_dir = sys.argv[3]
payload = json.loads(source.read_text(encoding="utf-8"))
payload["output_dir"] = output_dir
target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

uv run --project "${ENV_DIR}" --group dev python - <<'PY' \
    | tee "${RUN_DIR}/environment.json"
import json
import platform
from importlib.metadata import version

payload = {
    "python": platform.python_version(),
    "sktime": version("sktime"),
    "statsmodels": version("statsmodels"),
    "numpy": version("numpy"),
    "pandas": version("pandas"),
}
assert payload["sktime"] == "1.0.1", payload
print(json.dumps(payload, indent=2, sort_keys=True))
PY

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign"
    "${ROOT}/scripts/run_sktime_p2_benchmark.py"
    "${ROOT}/scripts/verify_sktime_p2_run.py"
    "${ROOT}/tests/sktime_campaign"
)

uv run --project "${ENV_DIR}" --group dev \
    python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q "${ROOT}/tests/sktime_campaign" \
    | tee "${LOG_DIR}/focused-pytest.log"

set +e
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_p2_benchmark.py" \
    --request "${REQUEST_FILE}" \
    | tee "${LOG_DIR}/provider.log"
PROVIDER_RC="${PIPESTATUS[0]}"
set -e

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p2_run.py" \
    --request "${REQUEST_FILE}" \
    --run "${RUN_DIR}/benchmark" \
    --allow-partial \
    | tee "${LOG_DIR}/evidence-verification.log"

if [[ "${PROVIDER_RC}" -ne 0 ]]; then
    printf 'SKTIME_P2_STATUS=NON_PASS_EVIDENCE_VERIFIED\n'
    exit "${PROVIDER_RC}"
fi

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p2_run.py" \
    --request "${REQUEST_FILE}" \
    --run "${RUN_DIR}/benchmark" \
    | tee "${LOG_DIR}/formal-verification.log"

(
    cd "${RUN_DIR}/benchmark"
    sha256sum -c SHA256SUMS
)

printf 'SKTIME_P2_STATUS=VERIFIED\n'
