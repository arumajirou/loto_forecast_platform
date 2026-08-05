#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-gluonts-p7d-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_ROOT="${1:-${ROOT}/artifacts/gluonts-p7d/${RUN_ID}}"
ARCHIVE="${2:-${RUN_ROOT%/}.zip}"

set +e
RUN_ID="${RUN_ID}" \
bash "${ROOT}/environments/gluonts-p7c-target-machine.sh" \
  "${RUN_ROOT}"
P7C_RC=$?
set -e

if [[ "${P7C_RC}" != 0 && "${P7C_RC}" != 10 && "${P7C_RC}" != 20 ]]; then
  echo "P7D_BLOCKED=P7C did not produce a handoff state: rc=${P7C_RC}" >&2
  exit 2
fi

bash "${ROOT}/environments/gluonts-p7d-export.sh" \
  "${RUN_ROOT}" \
  "${ARCHIVE}"

printf '%s\n' "P7D_RUN_ID=${RUN_ID}"
printf '%s\n' "P7D_RUN_ROOT=${RUN_ROOT}"
printf '%s\n' "P7D_ARCHIVE=${ARCHIVE}"
printf '%s\n' "P7D_P7C_RC=${P7C_RC}"
exit "${P7C_RC}"
