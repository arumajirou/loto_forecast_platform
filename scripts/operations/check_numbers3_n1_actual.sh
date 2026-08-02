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
SYNC_NUMBERS3_N1_FROM_POSTGRES="${PROJECT_ROOT}/scripts/operations/sync_numbers3_n1_from_postgres.py"
SYNC_RESULT_DIR="${PROJECT_ROOT}/logs/data-refresh-audit"
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

mkdir -p "${SYNC_RESULT_DIR}"

SYNC_RESULT="${SYNC_RESULT_DIR}/numbers3-n1-monitor-sync-${RUN_ID}.json"

echo "SYNC_SCRIPT=${SYNC_NUMBERS3_N1_FROM_POSTGRES}"
echo "SYNC_RESULT=${SYNC_RESULT}"

if test ! -f "${SYNC_NUMBERS3_N1_FROM_POSTGRES}"
then
  echo "ERROR: Numbers3 N1 PostgreSQL sync script is missing"
  echo "STATUS=SYNC_FAILED"
  echo "MONITORING_ACTION=RETRY"
  exit 1
fi

"${PROJECT_ROOT}/.venv/bin/python" \
  "${SYNC_NUMBERS3_N1_FROM_POSTGRES}" \
  --target "${DATA}" |
tee "${SYNC_RESULT}"

SYNC_RC=${PIPESTATUS[0]}

echo "SYNC_RC=${SYNC_RC}"

if test "${SYNC_RC}" -ne 0
then
  echo "ERROR: Numbers3 N1 PostgreSQL sync failed"
  echo "STATUS=SYNC_FAILED"
  echo "MONITORING_ACTION=RETRY"
  exit "${SYNC_RC}"
fi

"${PROJECT_ROOT}/.venv/bin/python" - \
  "${SYNC_RESULT}" <<'PY_SYNC'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

payload = json.loads(
    path.read_text(encoding="utf-8")
)

assert payload["status"] == "PASS"
assert payload["source_rows"] == payload["output_rows"]
assert payload["duplicate_ds"] == 0
assert payload["null_ds"] == 0
assert payload["null_y"] == 0

print(
    "SYNC_STATUS="
    f"{payload['status']}"
)
print(
    "SYNC_CHANGED="
    f"{str(payload['changed']).lower()}"
)
print(
    "SYNC_MAX_DS="
    f"{payload['max_ds']}"
)
print(
    "SYNC_OUTPUT_SHA256="
    f"{payload['output_sha256']}"
)
PY_SYNC

SYNC_VERIFY_RC=$?

echo "SYNC_VERIFY_RC=${SYNC_VERIFY_RC}"

if test "${SYNC_VERIFY_RC}" -ne 0
then
  echo "ERROR: Numbers3 N1 synchronization contract failed"
  echo "STATUS=SYNC_CONTRACT_FAILED"
  echo "MONITORING_ACTION=RETRY"
  exit "${SYNC_VERIFY_RC}"
fi

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
    echo "MONITORING_ACTION=CONTINUE"
    exit 0
    ;;

  PASS|ALREADY_REGISTERED)
    COMPLETION_DIR="${RESULT_DIR}/completion"
    COMPLETION_FILE="${COMPLETION_DIR}/CURRENT_ACTUAL_EVALUATION_COMPLETE.json"

    mkdir -p "${COMPLETION_DIR}"

    LOCK_SHA256="$(
      sha256sum "${CURRENT_LOCK}" |
      awk '{print $1}'
    )"

    COMPLETED_AT_UTC="$(
      date -u --iso-8601=seconds
    )"

    python3 -       "${COMPLETION_FILE}"       "${STATUS}"       "${CURRENT_LOCK}"       "${LOCK_SHA256}"       "${COMPLETED_AT_UTC}" <<'PY_COMPLETE'
import json
import os
import sys
import tempfile
from pathlib import Path

output = Path(sys.argv[1])

payload = {
    "schema_version": "1.0",
    "status": sys.argv[2],
    "source_lock": str(
        Path(sys.argv[3]).resolve()
    ),
    "source_lock_sha256": sys.argv[4],
    "completed_at_utc": sys.argv[5],
    "monitoring_action": (
        "TIMER_DISABLED_AFTER_COMPLETION"
    ),
}

output.parent.mkdir(
    parents=True,
    exist_ok=True,
)

fd, temporary_name = tempfile.mkstemp(
    prefix=f".{output.name}.",
    dir=output.parent,
    text=True,
)

temporary = Path(temporary_name)

try:
    with os.fdopen(
        fd,
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())

    temporary.replace(output)
finally:
    if temporary.exists():
        temporary.unlink()

print(f"COMPLETION_FILE={output}")
PY_COMPLETE

    sha256sum       "${COMPLETION_FILE}"       > "${COMPLETION_FILE}.sha256"

    (
      cd "${COMPLETION_DIR}"
      sha256sum -c         "$(basename "${COMPLETION_FILE}.sha256")"
    )

    if command -v systemctl >/dev/null 2>&1
    then
      systemctl --user disable         loto-numbers3-n1-actual-check.timer         || true

      systemctl --user stop         loto-numbers3-n1-actual-check.timer         || true
    fi

    echo "MONITORING_ACTION=TIMER_DISABLED_AFTER_COMPLETION"
    exit 0
    ;;

  *)
    echo "ERROR: unexpected status: ${STATUS}"
    exit 1
    ;;
esac
