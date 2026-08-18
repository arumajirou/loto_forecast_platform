#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
RUNNER="$REPO_ROOT/scripts/run_resource_aware_broad_campaign.py"
VERIFIER="$SCRIPT_DIR/runtime_audit/taj19_acceptance.py"
GPU_PREFLIGHT="$SCRIPT_DIR/runtime_audit/taj19_gpu_preflight.py"
BASE_ROOT="${TAJ19_ROOT:-$REPO_ROOT/runs/taj19-broad-runtime}"
CURRENT_FILE="$BASE_ROOT/CURRENT"
MODE="${1:-status}"
EXPECTED_PAIRS=1044

fail() {
    echo "TAJ19_STATUS=BLOCKED"
    echo "REASON=$*"
    echo "HOLDOUT=CLOSED"
    echo "PROSPECTIVE=CLOSED"
    exit 20
}

python_cmd() {
    if command -v uv >/dev/null 2>&1; then
        printf '%s\0' uv run --frozen python
    elif command -v python3 >/dev/null 2>&1; then
        printf '%s\0' python3
    else
        fail "uv/python3 is required"
    fi
}

readarray -d '' -t PY_CMD < <(python_cmd)

resolve_loto3() {
    if [[ -n "${TAJ19_LOTO3:-}" ]]; then
        [[ -x "$TAJ19_LOTO3" ]] || fail "TAJ19_LOTO3 is not executable: $TAJ19_LOTO3"
        printf '%s\n' "$TAJ19_LOTO3"
        return
    fi
    if command -v loto3 >/dev/null 2>&1; then
        command -v loto3
        return
    fi
    if command -v uv >/dev/null 2>&1; then
        local candidate
        candidate="$(uv run --frozen which loto3 2>/dev/null || true)"
        [[ -n "$candidate" && -x "$candidate" ]] || fail "loto3 executable is not available in the frozen uv runtime"
        printf '%s\n' "$candidate"
        return
    fi
    fail "loto3 executable not found"
}

progress_filter() {
    local line current total rest pct
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" =~ ^\[([0-9]+)/([0-9]+)\][[:space:]](.*)$ ]]; then
            current="${BASH_REMATCH[1]}"
            total="${BASH_REMATCH[2]}"
            rest="${BASH_REMATCH[3]}"
            if (( total > 0 )); then
                pct="$(printf '%d.%02d' $(( current * 100 / total )) $(( (current * 10000 / total) % 100 )))"
            else
                pct="0.00"
            fi
            printf '[%d/%d] %6s%% %s\n' "$current" "$total" "$pct" "$rest"
        else
            printf '%s\n' "$line"
        fi
    done
}

current_root() {
    [[ -f "$CURRENT_FILE" ]] || fail "no TAJ-19 current run exists"
    local root
    root="$(head -n 1 "$CURRENT_FILE")"
    [[ -n "$root" && -d "$root" ]] || fail "TAJ-19 current run root is invalid: $root"
    printf '%s\n' "$root"
}

show_status() {
    echo "TAJ19_LAUNCHER=v1"
    echo "REPO_ROOT=$REPO_ROOT"
    echo "REPO_HEAD=$(git -C "$REPO_ROOT" rev-parse HEAD)"
    echo "EXPECTED_BROAD_MODELS=174"
    echo "EXPECTED_GAMES=6"
    echo "EXPECTED_PAIRS=$EXPECTED_PAIRS"
    echo "HOLDOUT=CLOSED"
    echo "PROSPECTIVE=CLOSED"
    if [[ ! -f "$CURRENT_FILE" ]]; then
        echo "CURRENT_RUN=NONE"
        echo "PROGRESS=0/$EXPECTED_PAIRS"
        return 0
    fi
    local root campaign done pct
    root="$(head -n 1 "$CURRENT_FILE")"
    campaign="$root/campaign"
    done=0
    if [[ -d "$campaign/cases" ]]; then
        done="$(find "$campaign/cases" -type f -name FINAL.json -print 2>/dev/null | wc -l)"
    fi
    pct=$(( done * 100 / EXPECTED_PAIRS ))
    echo "CURRENT_RUN=$root"
    printf 'PROGRESS_BAR=['
    local filled=$(( pct * 40 / 100 ))
    local empty=$(( 40 - filled ))
    printf '%*s' "$filled" '' | tr ' ' '#'
    printf '%*s' "$empty" '' | tr ' ' '-'
    printf '] %d%% %d/%d\n' "$pct" "$done" "$EXPECTED_PAIRS"
    if [[ -f "$campaign/CAMPAIGN_SUMMARY.json" ]]; then
        "${PY_CMD[@]}" - "$campaign/CAMPAIGN_SUMMARY.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text(encoding="utf-8"))
print("TAJ19_ACCEPTANCE=" + str(data.get("acceptance", "UNKNOWN")))
for key, value in sorted(data.get("normalized_status_counts", {}).items()):
    print(f"STATUS_{key}={value}")
PY
    fi
}

new_run_root() {
    mkdir -p "$BASE_ROOT"
    local stamp root
    stamp="$(date -u +%Y%m%d-%H%M%S)"
    root="$BASE_ROOT/taj19-broad-$stamp"
    [[ ! -e "$root" ]] || fail "run root already exists: $root"
    mkdir -p "$root"
    printf '%s\n' "$root" > "$CURRENT_FILE.tmp"
    mv "$CURRENT_FILE.tmp" "$CURRENT_FILE"
    printf '%s\n' "$root"
}

run_preflight() {
    local root="$1"
    local plan_root="$root/preflight-plan"
    echo "[1/4]  25% freeze live Broad v1 inventory and resource plan"
    "${PY_CMD[@]}" "$RUNNER" \
        --output "$plan_root" \
        --models all \
        --games all \
        --outer-worker-cap "${TAJ19_OUTER_WORKER_CAP:-8}" \
        --cpus-per-trial "${TAJ19_CPUS_PER_TRIAL:-2}" \
        --ram-per-cpu-job-mib "${TAJ19_RAM_PER_CPU_JOB_MIB:-6144}" \
        --gpu-slot-mib "${TAJ19_GPU_SLOT_MIB:-5120}" \
        --gpu-safety-margin-mib "${TAJ19_GPU_SAFETY_MARGIN_MIB:-2048}" \
        --plan-only
    "${PY_CMD[@]}" "$VERIFIER" preflight --root "$plan_root"
    "${PY_CMD[@]}" "$GPU_PREFLIGHT" --root "$plan_root"
}

execute_campaign() {
    local root="$1"
    local resume_flag="${2:-}"
    local campaign="$root/campaign"
    local loto3
    local rc=0
    loto3="$(resolve_loto3)"
    echo "[2/4]  50% execute Broad 174 x 6 runtime matrix"
    echo "CAMPAIGN_ROOT=$campaign"
    echo "LOTO3=$loto3"
    set +e
    "${PY_CMD[@]}" "$RUNNER" \
        --output "$campaign" \
        --models all \
        --games all \
        --synthetic-rows "${TAJ19_SYNTHETIC_ROWS:-160}" \
        --seeds "${TAJ19_SEEDS:-1}" \
        --folds "${TAJ19_FOLDS:-1}" \
        --test-size "${TAJ19_TEST_SIZE:-2}" \
        --min-train-size "${TAJ19_MIN_TRAIN_SIZE:-80}" \
        --holdout-size "${TAJ19_HOLDOUT_SIZE:-4}" \
        --precision "${TAJ19_PRECISION:-32}" \
        --max-trials "${TAJ19_MAX_TRIALS:-1}" \
        --parallel-trials "${TAJ19_PARALLEL_TRIALS:-1}" \
        --outer-worker-cap "${TAJ19_OUTER_WORKER_CAP:-8}" \
        --cpus-per-trial "${TAJ19_CPUS_PER_TRIAL:-2}" \
        --ram-per-cpu-job-mib "${TAJ19_RAM_PER_CPU_JOB_MIB:-6144}" \
        --gpu-slot-mib "${TAJ19_GPU_SLOT_MIB:-5120}" \
        --gpu-safety-margin-mib "${TAJ19_GPU_SAFETY_MARGIN_MIB:-2048}" \
        --timeout "${TAJ19_TIMEOUT:-1200}" \
        --timellm-timeout "${TAJ19_TIMELLM_TIMEOUT:-5400}" \
        --timellm-max-steps "${TAJ19_TIMELLM_MAX_STEPS:-5}" \
        --loto3 "$loto3" \
        $resume_flag \
        2>&1 | progress_filter | tee "$root/CAMPAIGN.log"
    rc=${PIPESTATUS[0]}
    set -e
    echo "RUNNER_RC=$rc"
    return "$rc"
}

verify_campaign() {
    local root="$1"
    local campaign="$root/campaign"
    echo "[3/4]  75% verify 1,044 explicit statuses and functional evidence"
    "${PY_CMD[@]}" "$VERIFIER" verify --root "$campaign"
    echo "[4/4] 100% TAJ-19 evidence finalized"
    echo "RUN_ROOT=$root"
    echo "CAMPAIGN_ROOT=$campaign"
    echo "NEXT_ON_PASS=TAJ-20 unified 250 x 6 certification"
}

case "$MODE" in
    status)
        show_status
        ;;
    plan)
        ROOT="$(new_run_root)"
        run_preflight "$ROOT"
        echo "TAJ19_PLAN_ONLY=PASS"
        echo "RUN_ROOT=$ROOT"
        ;;
    run)
        ROOT="$(new_run_root)"
        run_preflight "$ROOT"
        RC=0
        execute_campaign "$ROOT" || RC=$?
        verify_campaign "$ROOT" || RC=$?
        exit "$RC"
        ;;
    resume)
        ROOT="$(current_root)"
        [[ -d "$ROOT/preflight-plan" ]] || run_preflight "$ROOT"
        RC=0
        execute_campaign "$ROOT" "--resume" || RC=$?
        verify_campaign "$ROOT" || RC=$?
        exit "$RC"
        ;;
    verify)
        ROOT="$(current_root)"
        verify_campaign "$ROOT"
        ;;
    *)
        echo "Usage: bash tools/taj19.sh {status|plan|run|resume|verify}"
        exit 2
        ;;
esac
