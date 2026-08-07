#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p1/${RUN_ID}}"
LOG_DIR="${RUN_DIR}/logs"
MAIN_LOG="${LOG_DIR}/certification.log"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P1_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P1_RUN_DIR=%s\n' "${RUN_DIR}"
    if [[ "${SKTIME_NO_PAUSE:-0}" != "1" && -t 0 ]]; then
        read -r -p "Press Enter to close..." _
    fi
    exit "${rc}"
}
trap finish EXIT

exec > >(tee -a "${MAIN_LOG}") 2>&1

printf 'SKTIME_P1_STATUS=EXECUTION_STARTED\n'
printf 'root=%s\n' "${ROOT}"
printf 'environment=%s\n' "${ENV_DIR}"
printf 'run_id=%s\n' "${RUN_ID}"
printf 'run_dir=%s\n' "${RUN_DIR}"

cd "${ROOT}"

test -f "${ENV_DIR}/pyproject.toml"
test -f "${ROOT}/scripts/run_sktime_provider.py"
test -f "${ROOT}/scripts/verify_sktime_p1_run.py"
test -f "${ROOT}/configs/sktime_campaign/smoke_matrix.json"
command -v git
command -v uv
command -v sha256sum

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'git_head=%s\n' "$(git rev-parse HEAD)"
    printf 'git_branch=%s\n' "$(git branch --show-current)"
    printf 'git_remote=%s\n' "$(git remote get-url origin)"
    printf 'uv_version=%s\n' "$(uv --version)"
    printf 'kernel=%s\n' "$(uname -srmo)"
} | tee "${RUN_DIR}/RUN_METADATA.txt"

git status --short | tee "${RUN_DIR}/git-status-before.txt"

uv lock --project "${ENV_DIR}"
test -s "${ENV_DIR}/uv.lock"
sha256sum "${ENV_DIR}/uv.lock" | tee "${RUN_DIR}/UV_LOCK_SHA256"

uv sync \
    --project "${ENV_DIR}" \
    --group dev \
    --frozen

export PYTHONPATH="${ROOT}/src"
export PYTHONHASHSEED=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

uv run --project "${ENV_DIR}" --group dev python - <<'PY' \
    | tee "${RUN_DIR}/environment.json"
import json
import platform
from importlib.metadata import version

payload = {
    "python": platform.python_version(),
    "platform": platform.platform(),
    "sktime": version("sktime"),
    "numpy": version("numpy"),
    "pandas": version("pandas"),
    "pydantic": version("pydantic"),
    "scikit-learn": version("scikit-learn"),
    "scipy": version("scipy"),
    "statsmodels": version("statsmodels"),
}
assert payload["sktime"] == "1.0.1", payload
print(json.dumps(payload, indent=2, sort_keys=True))
PY

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign"
    "${ROOT}/scripts/run_sktime_provider.py"
    "${ROOT}/scripts/verify_sktime_p0_run.py"
    "${ROOT}/scripts/verify_sktime_p1_run.py"
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
    | tee "${RUN_DIR}/focused-pytest.log"

mkdir -p "${RUN_DIR}/inventory" "${RUN_DIR}/smoke-matrix"

cat > "${RUN_DIR}/inventory-request.json" <<JSON
{
  "schema_version": "1.0",
  "operation": "inventory",
  "output_dir": "${RUN_DIR}/inventory",
  "environment_lane": "classic-py312",
  "expected_sktime_version": "1.0.1",
  "device": "cpu",
  "seed": 1
}
JSON

python - \
    "${ROOT}/configs/sktime_campaign/smoke_matrix.json" \
    "${RUN_DIR}/smoke-matrix-request.json" \
    "${RUN_DIR}/smoke-matrix" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
output_dir = sys.argv[3]
payload = json.loads(source.read_text(encoding="utf-8"))
payload["output_dir"] = output_dir
target.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_provider.py" \
    --request "${RUN_DIR}/inventory-request.json" \
    | tee "${RUN_DIR}/inventory-provider.log"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_provider.py" \
    --request "${RUN_DIR}/smoke-matrix-request.json" \
    | tee "${RUN_DIR}/smoke-matrix-provider.log"

git status --short | tee "${RUN_DIR}/git-status-after.txt"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p1_run.py" \
    --run "${RUN_DIR}" \
    | tee "${RUN_DIR}/verification.log"

(
    cd "${RUN_DIR}"
    sha256sum -c SHA256SUMS
)

printf 'SKTIME_P1_STATUS=VERIFIED\n'
