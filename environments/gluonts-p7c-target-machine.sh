#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-gluonts-p7c-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${1:-${ROOT}/artifacts/gluonts-p7c/${RUN_ID}}"
P7B_OUT="${OUT}/p7b"
P7C_OUT="${OUT}/p7c"

if [[ -d "${OUT}" ]] && find "${OUT}" -mindepth 1 -print -quit | grep -q .; then
  echo "P7C_REFUSED=output directory is not empty: ${OUT}" >&2
  exit 2
fi
mkdir -p "${OUT}"
printf '%s\n' "${RUN_ID}" > "${OUT}/RUN_ID"

set +e
RUN_ID="${RUN_ID}" \
bash "${ROOT}/environments/gluonts-p7b-target-machine.sh" \
  "${P7B_OUT}" \
  > "${OUT}/p7b.stdout.log" \
  2> "${OUT}/p7b.stderr.log"
P7B_RC=$?
set -e
printf '%s\n' "${P7B_RC}" > "${OUT}/p7b.rc"

if [[ -f "${P7B_OUT}/P7B_EXECUTION_COMPLETE" ]]; then
  set +e
  bash "${ROOT}/environments/gluonts-p7c-analyze.sh" \
    "${P7B_OUT}" \
    "${P7C_OUT}" \
    > "${OUT}/p7c.stdout.log" \
    2> "${OUT}/p7c.stderr.log"
  P7C_RC=$?
  set -e
else
  P7C_RC=2
  printf '%s\n' \
    "P7C_SKIPPED=P7B execution is incomplete; resume P7B before analysis" \
    > "${OUT}/p7c.stderr.log"
  : > "${OUT}/p7c.stdout.log"
fi
printf '%s\n' "${P7C_RC}" > "${OUT}/p7c.rc"

(
  cd "${OUT}"
  find . -type f ! -name P7C_ORCHESTRATION_SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 sha256sum \
    > P7C_ORCHESTRATION_SHA256SUMS
)

cat "${OUT}/p7c.stdout.log"
printf '%s\n' "P7C_RUN_ID=${RUN_ID}"
printf '%s\n' "P7C_ARTIFACT_DIR=${OUT}"
printf '%s\n' "P7B_RC=${P7B_RC}"
printf '%s\n' "P7C_RC=${P7C_RC}"
exit "${P7C_RC}"
