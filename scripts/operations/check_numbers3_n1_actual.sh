#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." &&
  pwd
)"

TOOL="${PROJECT_ROOT}/tools/nf_loto_research_closure"
LOCK_DIR="${PROJECT_ROOT}/prospective/numbers3-n1/locks"
RESULT_DIR="${PROJECT_ROOT}/prospective/numbers3-n1/evaluations"
DATA="${PROJECT_ROOT}/data/exports/numbers3/numbers3_n1.parquet"
LOG_DIR="${PROJECT_ROOT}/logs/prospective-actual-watch"

mkdir -p \
  "${RESULT_DIR}" \
  "${LOG_DIR}"

RUN_ID="$(
  date -u +%Y%m%d-%H%M%S
)"

LOG="${LOG_DIR}/check-${RUN_ID}.log"

exec > >(
  tee -a "${LOG}"
) 2>&1

echo "RUN_ID=${RUN_ID}"
echo "STARTED_AT_UTC=$(date -u --iso-8601=seconds)"
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "DATA=${DATA}"

test -s "${DATA}" || {
  echo "STATUS=DATA_NOT_AVAILABLE"
  exit 0
}

CURRENT_LOCK="$(
  readlink -f \
    "${LOCK_DIR}/CURRENT.json"
)"

test -s "${CURRENT_LOCK}" || {
  echo "STATUS=LOCK_NOT_AVAILABLE"
  exit 0
}

cd "${PROJECT_ROOT}"

OUTPUT="$(
  uv run \
    --project "${TOOL}" \
    python \
    "${TOOL}/scripts/evaluate_when_actual_available.py" \
    --lock "${CURRENT_LOCK}" \
    --data "${DATA}" \
    --output-dir "${RESULT_DIR}" \
    --register-script \
      "${TOOL}/scripts/register_prospective_actual.py"
)"

printf '%s\n' "${OUTPUT}"

STATUS="$(
  printf '%s' "${OUTPUT}" |
  uv run \
    --project "${TOOL}" \
    python -c '
import json
import sys

payload = json.load(sys.stdin)
print(payload.get("status", "UNKNOWN"))
'
)"

echo "STATUS=${STATUS}"
echo "FINISHED_AT_UTC=$(date -u --iso-8601=seconds)"

case "${STATUS}" in
  WAITING_FOR_ACTUAL)
    exit 0
    ;;
  ALREADY_REGISTERED)
    exit 0
    ;;
  PASS)
    exit 0
    ;;
  *)
    echo "ERROR: unexpected status: ${STATUS}"
    exit 1
    ;;
esac
