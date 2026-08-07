#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${1:-/mnt/e/env/ts/loto_forecast_platform-harness-20260804-194725}"
SOURCE_REPORT="${2:?usage: run_model_switch_ab.sh ROOT SOURCE_REPORT [CANDIDATE_MODEL]}"
CANDIDATE_MODEL="${3:-gemini-3.6-flash}"

ROOT="$(realpath "${ROOT}")"
SOURCE_REPORT="$(realpath "${SOURCE_REPORT}")"

test -s "${SOURCE_REPORT}"

python3 - "${SOURCE_REPORT}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
acceptance = data.get("acceptance", {})
switch_required = (
    not acceptance.get("candidate_beats_generic", False)
    or not acceptance.get("eligible_modes", [])
    or data.get("best_mode") is None
)
if not switch_required:
    raise SystemExit("BLOCKED: source model still has an eligible improving profile")
print("MODEL_SWITCH_CONDITION=VERIFIED")
print(f"source_model={data.get('model')}")
print(f"source_report={path.resolve()}")
PY

if [ "${CANDIDATE_MODEL}" = "gemini-3.6-flash" ]; then
    test -n "${GEMINI_API_KEY:-}" || {
        echo "BLOCKED: GEMINI_API_KEY is not configured" >&2
        exit 2
    }
fi

RUN_ID="$(date +%Y%m%d-%H%M%S)"
BASE="${ROOT}/artifacts/harness/model-switch/${CANDIDATE_MODEL}/${RUN_ID}"
AUDIT="${BASE}/profile-audit.json"
REPORT="${BASE}/profile-ab.json"
LOG="${BASE}/profile-ab.log"
EXIT_FILE="${BASE}/exit_code.txt"
STATUS_FILE="${BASE}/status.txt"
SOURCE_FILE="${BASE}/source-report.txt"

mkdir -p "${BASE}"
printf '%s\n' "${SOURCE_REPORT}" > "${SOURCE_FILE}"

uv run \
  --extra harness \
  loto-harness profile-audit \
  "${CANDIDATE_MODEL}" \
  --modes generic,fast,quality,reasoning,tools,structured \
  --output "${AUDIT}"

sha256sum -c "${AUDIT}.sha256"

set +e
uv run \
  --extra harness \
  loto-harness profile-ab \
  "${CANDIDATE_MODEL}" \
  --modes generic,fast,quality,reasoning,tools,structured \
  --repetitions 5 \
  --context-tokens 16384 \
  --context-utilization 0.90 \
  --seed 1 \
  --output "${REPORT}" \
  2>&1 | tee "${LOG}"
rc=${PIPESTATUS[0]}
set -e

printf '%s\n' "${rc}" > "${EXIT_FILE}"
case "${rc}" in
  0) printf 'VERIFIED\n' > "${STATUS_FILE}" ;;
  3) printf 'ACCEPTANCE_FAILED\n' > "${STATUS_FILE}" ;;
  *) printf 'RUNTIME_FAILED\n' > "${STATUS_FILE}" ;;
esac

test -s "${REPORT}"
test -s "${REPORT}.sha256"
sha256sum -c "${REPORT}.sha256"

sha256sum \
  "${AUDIT}" \
  "${AUDIT}.sha256" \
  "${REPORT}" \
  "${REPORT}.sha256" \
  "${LOG}" \
  "${EXIT_FILE}" \
  "${STATUS_FILE}" \
  "${SOURCE_FILE}" \
  > "${BASE}/SHA256SUMS"

(
  cd "${BASE}"
  sha256sum -c SHA256SUMS
)

echo "MODEL_SWITCH_AB=COMPLETED"
echo "candidate_model=${CANDIDATE_MODEL}"
echo "output=${BASE}"
echo "audit=${AUDIT}"
echo "report=${REPORT}"
echo "log=${LOG}"
echo "exit_file=${EXIT_FILE}"
echo "status_file=${STATUS_FILE}"
echo "sha256=${BASE}/SHA256SUMS"
exit 0
