#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-/mnt/e/env/ts/loto_forecast_platform}"
PROFILE="${PROFILE:-overnight}"
PARALLEL="${PARALLEL:-2}"
TIMEOUT="${TIMEOUT:-3600}"
MAX_RUNS="${MAX_RUNS:-500}"
DEVICE="${DEVICE:-auto}"
SEED="${SEED:-42}"

cd "$PROJECT" || exit 1

STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_ROOT="/mnt/e/env/ts/logs/overnight-model-matrix-${STAMP}"
mkdir -p "$LOG_ROOT"

SCRIPT="$PROJECT/scripts/overnight_model_matrix.py"
if [[ ! -f "$SCRIPT" ]]; then
  echo "Missing $SCRIPT" >&2
  exit 2
fi

# Do not run multiple campaigns accidentally.
LOCK="/tmp/loto-overnight-model-matrix.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "Another overnight matrix is already running." >&2
  exit 3
fi

ulimit -Sn 8192 2>/dev/null || true

echo "$$" > "$LOG_ROOT/launcher.pid"
env | sort > "$LOG_ROOT/environment.txt"
git status --short --branch > "$LOG_ROOT/git-status-before.txt" 2>&1 || true
git rev-parse HEAD > "$LOG_ROOT/git-head.txt" 2>&1 || true
uv run python --version > "$LOG_ROOT/python-version.txt" 2>&1 || true
nvidia-smi > "$LOG_ROOT/nvidia-smi-before.txt" 2>&1 || true

set +e
uv run python "$SCRIPT" \
  --profile "$PROFILE" \
  --parallel "$PARALLEL" \
  --timeout "$TIMEOUT" \
  --max-runs "$MAX_RUNS" \
  --device "$DEVICE" \
  --seed "$SEED" \
  2>&1 | tee "$LOG_ROOT/launcher.log"
RC=${PIPESTATUS[0]}
set -e

nvidia-smi > "$LOG_ROOT/nvidia-smi-after.txt" 2>&1 || true
echo "$RC" > "$LOG_ROOT/exit-code.txt"

LATEST="$(find runs/overnight-model-matrix -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2-)"
if [[ -n "${LATEST:-}" ]]; then
  ln -sfn "$PROJECT/$LATEST" "$LOG_ROOT/campaign"
  cp -f "$LATEST/summary.json" "$LOG_ROOT/" 2>/dev/null || true
  cp -f "$LATEST/REPORT.md" "$LOG_ROOT/" 2>/dev/null || true
fi

echo "OVERNIGHT_RC=$RC"
echo "LOG_ROOT=$LOG_ROOT"
echo "CAMPAIGN=${LATEST:-unknown}"
exit "$RC"
