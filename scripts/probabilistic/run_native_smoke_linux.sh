#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONFIG="${2:-${ROOT}/configs/probabilistic/native_smoke.yaml}"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="${ROOT}/artifacts/probabilistic-native-smoke-${STAMP}"
mkdir -p "${LOG_DIR}"
cd "${ROOT}"

uv run python tools/verify_native_ppl_implementation.py \
  --root "${ROOT}" \
  --require-runtime \
  --output "${LOG_DIR}/native-verification.json"

uv run loto3 probabilistic native-coverage > "${LOG_DIR}/native-coverage.json"
uv run loto3 probabilistic plan --config "${CONFIG}" > "${LOG_DIR}/plan.json"

uv run python - "${LOG_DIR}/plan.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
assert data["models_requested"] == 72, data
assert data["trials_total"] == 72, data
assert data["trials_allowed"] == 72, data
assert data["trials_blocked"] == 0, data
print("PPL01_NATIVE_PLAN=PASS")
PY

set -o pipefail
uv run loto3 probabilistic smoke --config "${CONFIG}" \
  | tee "${LOG_DIR}/run.json"
status=${PIPESTATUS[0]}

uv run python - "${LOG_DIR}/run.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
assert data["status"] == "PASS", data
assert data["models_planned"] == 72, data
assert data["trials_total"] == 72, data
assert data["status_counts"] == {"PASS": 72}, data
print("PPL01_NATIVE_SMOKE=PASS")
PY

printf 'PPL01_NATIVE_SMOKE_EXIT_CODE=%s\n' "${status}"
printf 'LOG_DIR=%s\n' "${LOG_DIR}"
exit "${status}"
