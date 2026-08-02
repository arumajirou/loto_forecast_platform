#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REASON="${1:-manual}"
RUNTIME_ENV="${LOTO_OPS_RUNTIME_ENV:-$HOME/.config/loto-ops/runtime.env}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/loto-ops"
LOG_DIR="$ROOT/logs/scheduler"
LOCK_FILE="$STATE_DIR/pipeline.lock"
LAST_SUCCESS_DATE_FILE="$STATE_DIR/last_success_date"
LAST_JSON="$LOG_DIR/last_run.json"
PROGRESS_JSON="$LOG_DIR/progress.json"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/${REASON}_${TS}.log"
TOTAL_STEPS=3
NOTIFY_ARMED=0
STARTED_AT=""

mkdir -p "$STATE_DIR" "$LOG_DIR" "$ROOT/runs" "$ROOT/artifacts/reports" "$ROOT/artifacts/zips"

if [[ -f "$RUNTIME_ENV" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$RUNTIME_ENV"
    set +a
fi

export LOTO_OPS_PROJECT="$ROOT"
export LOTO_OPS_CONFIG="${LOTO_OPS_CONFIG:-$ROOT/configs/loto_ops.yaml}"
export LOTO_LIFE_PROJECT="${LOTO_LIFE_PROJECT:-/mnt/e/env/ts/loto_life_feature_pipeline}"
export LOTO_FORECAST_PROJECT="${LOTO_FORECAST_PROJECT:-/mnt/e/env/ts/loto_neuralforecast_pipeline}"
export LOTO_ZIP_OUTPUT_DIR="${LOTO_ZIP_OUTPUT_DIR:-/mnt/e/env/ts/zips}"
export DB_HOST="${DB_HOST:-127.0.0.1}"
export DB_PORT="${DB_PORT:-5432}"
export DB_USER="${DB_USER:-loto}"
export DB_NAME="${DB_NAME:-loto}"
export LOTO_OPS_MODE="${LOTO_OPS_MODE:-light}"
export PATH="$ROOT/.venv/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ -z "${DB_PASSWORD:-}" ]]; then
    echo "ERROR: DB_PASSWORD is not configured in $RUNTIME_ENV" | tee -a "$LOG_FILE"
    echo "Run: $ROOT/scripts/configure_runtime.sh" | tee -a "$LOG_FILE"
    exit 78
fi

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    echo "ERROR: virtual environment missing. Run: bash $ROOT/setup_linux.sh" | tee -a "$LOG_FILE"
    exit 69
fi

LOTO_OPS=("$ROOT/run_loto_ops.sh")
TODAY="$(date +%F)"
DOW="$(date +%u)"

should_use_daily_guard=0
case "$REASON" in
    startup|pc_startup|kubuntu_startup|weekday_daily|weekday_timer)
        should_use_daily_guard=1
        ;;
esac

if [[ "$REASON" == weekday_* && "$DOW" -ge 6 ]]; then
    echo "[$(date --iso-8601=seconds)] weekend: weekday timer skipped" | tee -a "$LOG_FILE"
    exit 0
fi

if [[ "$REASON" == startup || "$REASON" == pc_startup || "$REASON" == kubuntu_startup ]]; then
    if [[ "$DOW" -ge 6 && "${LOTO_OPS_STARTUP_RUN_WEEKENDS:-1}" == "0" ]]; then
        echo "[$(date --iso-8601=seconds)] weekend startup run disabled" | tee -a "$LOG_FILE"
        exit 0
    fi
fi

if [[ "$should_use_daily_guard" -eq 1 && -f "$LAST_SUCCESS_DATE_FILE" ]]; then
    if [[ "$(cat "$LAST_SUCCESS_DATE_FILE" 2>/dev/null || true)" == "$TODAY" ]]; then
        echo "[$(date --iso-8601=seconds)] already completed today; skip reason=$REASON" | tee -a "$LOG_FILE"
        exit 0
    fi
fi

progress_update() {
    local step="$1" name="$2" status="$3" message="${4:-}"
    "$ROOT/.venv/bin/python" "$ROOT/scripts/update_progress.py" \
        --state "$PROGRESS_JSON" \
        --title "loto-ops scheduled pipeline" \
        --reason "$REASON" \
        --step "$step" \
        --total "$TOTAL_STEPS" \
        --name "$name" \
        --status "$status" \
        --message "$message" \
        --log-file "$LOG_FILE" >>"$LOG_FILE" 2>&1
}

notify_final() {
    local rc=$?
    if [[ "$NOTIFY_ARMED" != "1" ]]; then
        return "$rc"
    fi

    local status="success"
    [[ "$rc" -ne 0 ]] && status="failed"
    local finished_at
    finished_at="$(date --iso-8601=seconds)"

    if [[ "$status" == "failed" ]]; then
        cat > "$LAST_JSON" <<JSON
{
  "status": "failed",
  "reason": "$REASON",
  "started_at": "$STARTED_AT",
  "finished_at": "$finished_at",
  "log_file": "$LOG_FILE",
  "progress_file": "$PROGRESS_JSON"
}
JSON
    fi

    if [[ "${LOTO_NOTIFY_ENABLED:-1}" != "0" ]]; then
        "${LOTO_OPS[@]}" notify-run-summary \
            --status "$status" \
            --reason "$REASON" \
            --log-file "$LOG_FILE" \
            --progress-file "$PROGRESS_JSON" \
            --last-run-file "$LAST_JSON" \
            >>"$LOG_FILE" 2>&1 || true
    fi
    return "$rc"
}
trap notify_final EXIT

run_step() {
    local step="$1" name="$2"
    shift 2
    progress_update "$step" "$name" running ""
    echo "[$(date --iso-8601=seconds)] >>> $name" | tee -a "$LOG_FILE"
    if "$@" 2>&1 | tee -a "$LOG_FILE"; then
        progress_update "$step" "$name" success done
        echo "[$(date --iso-8601=seconds)] <<< $name" | tee -a "$LOG_FILE"
    else
        local rc=${PIPESTATUS[0]}
        progress_update "$step" "$name" failed "rc=$rc"
        return "$rc"
    fi
}

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date --iso-8601=seconds)] another pipeline is already running" | tee -a "$LOG_FILE"
    exit 75
fi

# Wait up to five minutes for PostgreSQL after PC startup.
if command -v pg_isready >/dev/null 2>&1; then
    for _ in $(seq 1 30); do
        if pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
            break
        fi
        sleep 10
    done
fi

rm -f "$PROGRESS_JSON"
STARTED_AT="$(date --iso-8601=seconds)"
NOTIFY_ARMED=1

echo "[$STARTED_AT] scheduled pipeline started reason=$REASON" | tee -a "$LOG_FILE"
run_step 1 preflight "${LOTO_OPS[@]}" preflight --auto-fix
run_step 2 scrape "${LOTO_OPS[@]}" scrape --games all
run_step 3 run-all-fast "${LOTO_OPS[@]}" run-all-fast \
    --engine auto \
    --mode "$LOTO_OPS_MODE" \
    --unified-engine fast \
    --with-exog \
    --parallel-workers "${LOTO_EXOG_WORKERS:-16}" \
    --with-analysis \
    --package light

FINISHED_AT="$(date --iso-8601=seconds)"
printf '%s\n' "$TODAY" > "$LAST_SUCCESS_DATE_FILE"
cat > "$LAST_JSON" <<JSON
{
  "status": "success",
  "reason": "$REASON",
  "started_at": "$STARTED_AT",
  "finished_at": "$FINISHED_AT",
  "log_file": "$LOG_FILE",
  "progress_file": "$PROGRESS_JSON"
}
JSON
progress_update "$TOTAL_STEPS" finished success "pipeline finished"
echo "[$FINISHED_AT] scheduled pipeline finished" | tee -a "$LOG_FILE"
