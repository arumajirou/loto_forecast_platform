#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-core-py313"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p0/${RUN_ID}}"
LOG_DIR="${RUN_DIR}/logs"
MAIN_LOG="${LOG_DIR}/certification.log"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P0_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P0_RUN_DIR=%s\n' "${RUN_DIR}"
    if [[ "${SKTIME_NO_PAUSE:-0}" != "1" && -t 0 ]]; then
        read -r -p "Press Enter to close..." _
    fi
    exit "${rc}"
}
trap finish EXIT

exec > >(tee -a "${MAIN_LOG}") 2>&1

printf 'SKTIME_P0_STATUS=EXECUTION_STARTED\n'
printf 'root=%s\n' "${ROOT}"
printf 'environment=%s\n' "${ENV_DIR}"
printf 'run_id=%s\n' "${RUN_ID}"
printf 'run_dir=%s\n' "${RUN_DIR}"

cd "${ROOT}"

test -f "${ENV_DIR}/pyproject.toml"
test -f "${ROOT}/scripts/run_sktime_provider.py"
test -f "${ROOT}/scripts/verify_sktime_p0_run.py"
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
}
assert payload["sktime"] == "1.0.1", payload
print(json.dumps(payload, indent=2, sort_keys=True))
PY

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign"
    "${ROOT}/scripts/run_sktime_provider.py"
    "${ROOT}/scripts/verify_sktime_p0_run.py"
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

mkdir -p "${RUN_DIR}/inventory" "${RUN_DIR}/naive-smoke"

cat > "${RUN_DIR}/inventory-request.json" <<JSON
{
  "schema_version": "1.0",
  "operation": "inventory",
  "output_dir": "${RUN_DIR}/inventory",
  "environment_lane": "core-py313",
  "expected_sktime_version": "1.0.1",
  "device": "cpu",
  "seed": 1
}
JSON

cat > "${RUN_DIR}/naive-smoke-request.json" <<JSON
{
  "schema_version": "1.0",
  "operation": "naive_smoke",
  "output_dir": "${RUN_DIR}/naive-smoke",
  "environment_lane": "core-py313",
  "expected_sktime_version": "1.0.1",
  "model_name": "NaiveForecaster",
  "strategy": "last",
  "forecast_horizon": [1, 2],
  "series": [4, 7, 3, 8, 6, 9, 5, 10],
  "save_load": true,
  "device": "cpu",
  "seed": 1
}
JSON

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_provider.py" \
    --request "${RUN_DIR}/inventory-request.json" \
    | tee "${RUN_DIR}/inventory-provider.log"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_provider.py" \
    --request "${RUN_DIR}/naive-smoke-request.json" \
    | tee "${RUN_DIR}/naive-smoke-provider.log"

uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p0_run.py" \
    --run "${RUN_DIR}" \
    | tee "${RUN_DIR}/verification.log"

(
    cd "${RUN_DIR}"
    sha256sum -c SHA256SUMS
)

git status --short | tee "${RUN_DIR}/git-status-after.txt"
printf 'SKTIME_P0_STATUS=VERIFIED\n'
