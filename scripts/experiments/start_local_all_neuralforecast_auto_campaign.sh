#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
SESSION="all-auto-${RUN_ID}"
GROUP="${ROOT}/artifacts/miniloto-all-auto/campaign-${RUN_ID}"
LOG="${GROUP}.log"
EXIT_CODE_FILE="${GROUP}.exit_code"

mkdir -p "$(dirname "${LOG}")"

COMMAND="$(
cat <<INNER
cd "${ROOT}" || exit 1
set -o pipefail
RUN_ID="${RUN_ID}" \
  bash scripts/experiments/run_local_all_neuralforecast_auto_campaign.sh \
  2>&1 | tee "${LOG}"
rc=\${PIPESTATUS[0]}
printf '%s\n' "\${rc}" > "${EXIT_CODE_FILE}"
exit "\${rc}"
INNER
)"

tmux new-session \
  -d \
  -s "${SESSION}" \
  "bash -lc $(printf '%q' "${COMMAND}")"

echo "SESSION=${SESSION}"
echo "GROUP=${GROUP}"
echo "LOG=${LOG}"
echo "EXIT_CODE_FILE=${EXIT_CODE_FILE}"
echo "ATTACH=tmux attach -t ${SESSION}"
