#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
ENV_DIR="${ROOT}/environments/sktime-classic-py312"
ACTUALS_CONFIG="${SKTIME_P5_ACTUALS_CONFIG:-${ROOT}/configs/sktime_campaign/prospective_actuals.json}"
RUN_ID="${SKTIME_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${SKTIME_RUN_DIR:-${ROOT}/artifacts/sktime-p5-monitor/${RUN_ID}}"
EVIDENCE_DIR="${RUN_DIR}/prospective-monitoring"
LOG_DIR="${RUN_DIR}/logs"
EXIT_CODE_FILE="${RUN_DIR}/exit_code.txt"
REFERENCE_METRICS="${RUN_DIR}/HOLDOUT_REFERENCE_METRICS.json"

mkdir -p "${LOG_DIR}"

finish() {
    local rc=$?
    trap - EXIT
    printf '%s\n' "${rc}" > "${EXIT_CODE_FILE}"
    printf 'SKTIME_P5_MONITOR_EXIT_CODE=%s\n' "${rc}"
    printf 'SKTIME_P5_MONITOR_RUN_DIR=%s\n' "${RUN_DIR}"
    if [[ "${SKTIME_NO_PAUSE:-0}" != "1" && -t 0 ]]; then
        read -r -p "Press Enter to close..." _
    fi
    exit "${rc}"
}
trap finish EXIT
exec > >(tee -a "${LOG_DIR}/certification.log") 2>&1

cd "${ROOT}"
command -v uv
command -v sha256sum

test -s "${ACTUALS_CONFIG}"

P5_LOCK_DIR="${SKTIME_P5_LOCK_EVIDENCE_DIR:-}"
if [[ -z "${P5_LOCK_DIR}" ]]; then
    P5_LOCK_DIR="$({
        find "${ROOT}/artifacts/sktime-p5-lock" \
            -mindepth 2 \
            -maxdepth 2 \
            -type d \
            -name prospective-shadow-lock \
            -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
    } || true)"
fi
if [[ -z "${P5_LOCK_DIR}" || ! -d "${P5_LOCK_DIR}" ]]; then
    echo "BLOCKED: verified P5 lock evidence directory was not found"
    exit 2
fi
(
    cd "${P5_LOCK_DIR}"
    sha256sum -c SHA256SUMS
)

P5_LOCK="${P5_LOCK_DIR}/PROSPECTIVE_PREDICTION_LOCK.json"
test -s "${P5_LOCK}"
readarray -t LOCK_FIELDS < <(
    python - "${P5_LOCK_DIR}/response.json" "${P5_LOCK}" <<'PY'
import json
import sys
from pathlib import Path

response = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
lock = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if response.get("status") != "PASS":
    raise SystemExit("P5 lock response status is not PASS")
if response.get("prospective_status") != "PREDICTIONS_LOCKED_NOT_SCORED":
    raise SystemExit("P5 Prospective boundary mismatch")
if response.get("promotion_status") != "SHADOW_NOT_PROMOTED":
    raise SystemExit("P5 lock promotion boundary mismatch")
if response.get("actuals_known") is not False:
    raise SystemExit("P5 lock incorrectly claims actuals")
if lock.get("shadow_candidate_id") != response.get("shadow_candidate_id"):
    raise SystemExit("P5 shadow candidate mismatch")
print(response["shadow_candidate_id"])
print(lock["sealed_at_utc"])
PY
)
SHADOW_ID="${LOCK_FIELDS[0]}"
SEALED_AT_UTC="${LOCK_FIELDS[1]}"

P4_DIR="${SKTIME_P4_EVIDENCE_DIR:-}"
if [[ -z "${P4_DIR}" ]]; then
    P4_DIR="$({
        find "${ROOT}/artifacts/sktime-p4" \
            -mindepth 2 \
            -maxdepth 2 \
            -type d \
            -name sealed-holdout-score \
            -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
    } || true)"
fi
if [[ -z "${P4_DIR}" || ! -d "${P4_DIR}" ]]; then
    echo "BLOCKED: verified P4 evidence directory was not found"
    exit 2
fi
(
    cd "${P4_DIR}"
    sha256sum -c SHA256SUMS
)
python - \
    "${P4_DIR}/response.json" \
    "${P4_DIR}/HOLDOUT_CANDIDATE_AGGREGATES.json" \
    "${SHADOW_ID}" \
    "${REFERENCE_METRICS}" <<'PY'
import json
import sys
from pathlib import Path

response = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
aggregates = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
shadow_id = sys.argv[3]
if response.get("status") != "PASS":
    raise SystemExit("P4 response status is not PASS")
if response.get("selected_oof_candidate_id") != shadow_id:
    raise SystemExit("P4 and P5 shadow candidates differ")
selected = next(
    (
        row
        for row in aggregates
        if row.get("candidate_id") == shadow_id
        and row.get("status") == "PASS"
    ),
    None,
)
if not selected or "metrics" not in selected:
    raise SystemExit("P4 shadow Holdout reference metrics are unavailable")
Path(sys.argv[4]).write_text(
    json.dumps(selected["metrics"], indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

REVEALED_AT_UTC="${SKTIME_P5_REVEALED_AT_UTC:-}"
if [[ -z "${REVEALED_AT_UTC}" ]]; then
    REVEALED_AT_UTC="$({
        python - "${SEALED_AT_UTC}" <<'PY'
import sys
from datetime import UTC, datetime, timedelta

sealed = datetime.strptime(sys.argv[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
now = datetime.now(UTC).replace(microsecond=0)
print(max(now, sealed + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
PY
    })"
fi

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'p5_lock_dir=%s\n' "${P5_LOCK_DIR}"
    printf 'p5_lock_sha256=%s\n' "$(sha256sum "${P5_LOCK}" | awk '{print $1}')"
    printf 'p4_evidence_dir=%s\n' "${P4_DIR}"
    printf 'shadow_candidate_id=%s\n' "${SHADOW_ID}"
    printf 'sealed_at_utc=%s\n' "${SEALED_AT_UTC}"
    printf 'revealed_at_utc=%s\n' "${REVEALED_AT_UTC}"
    printf 'actuals_config_sha256=%s\n' "$(sha256sum "${ACTUALS_CONFIG}" | awk '{print $1}')"
    printf 'holdout_reference_sha256=%s\n' "$(sha256sum "${REFERENCE_METRICS}" | awk '{print $1}')"
} | tee "${RUN_DIR}/RUN_METADATA.txt"

uv lock --project "${ENV_DIR}"
test -s "${ENV_DIR}/uv.lock"
uv sync --project "${ENV_DIR}" --group dev --frozen
export PYTHONPATH="${ROOT}/src:${ROOT}/scripts"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

CHECK_PATHS=(
    "${ROOT}/src/loto/sktime_campaign/prospective.py"
    "${ROOT}/src/loto/sktime_campaign/prospective_artifacts.py"
    "${ROOT}/scripts/run_sktime_p5_monitor.py"
    "${ROOT}/scripts/verify_sktime_p5_monitor.py"
    "${ROOT}/tests/sktime_campaign/test_prospective.py"
    "${ROOT}/tests/sktime_campaign/test_prospective_artifacts.py"
)
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff format --check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m ruff check "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m compileall -q "${CHECK_PATHS[@]}"
uv run --project "${ENV_DIR}" --group dev \
    python -m pytest -q \
    "${ROOT}/tests/sktime_campaign/test_prospective.py" \
    "${ROOT}/tests/sktime_campaign/test_prospective_artifacts.py" \
    | tee "${RUN_DIR}/focused-pytest.log"

COMMON_ARGS=(
    --actuals-config "${ACTUALS_CONFIG}"
    --prediction-lock "${P5_LOCK}"
    --holdout-reference-metrics "${REFERENCE_METRICS}"
    --output "${EVIDENCE_DIR}"
    --run-id "${RUN_ID}"
    --revealed-at-utc "${REVEALED_AT_UTC}"
)

set +e
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/run_sktime_p5_monitor.py" \
    "${COMMON_ARGS[@]}" \
    | tee "${LOG_DIR}/monitoring.log"
MONITOR_RC=${PIPESTATUS[0]}
set -e

VERIFY_ARGS=("${COMMON_ARGS[@]}")
if [[ "${MONITOR_RC}" -ne 0 ]]; then
    VERIFY_ARGS+=(--allow-nonpass)
fi
uv run --project "${ENV_DIR}" --group dev \
    python "${ROOT}/scripts/verify_sktime_p5_monitor.py" \
    "${VERIFY_ARGS[@]}" \
    | tee "${LOG_DIR}/verification.log"

(
    cd "${EVIDENCE_DIR}"
    sha256sum -c SHA256SUMS
)

if [[ "${MONITOR_RC}" -ne 0 ]]; then
    echo "SKTIME_P5_MONITOR_STATUS=EVIDENCE_VERIFIED_NONPASS"
    exit "${MONITOR_RC}"
fi

echo "SKTIME_P5_MONITOR_STATUS=VERIFIED"
