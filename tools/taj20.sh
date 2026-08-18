#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
PLANNER="$REPO_ROOT/scripts/plan_all_execution_identities.py"
PREFLIGHT="$SCRIPT_DIR/runtime_audit/taj20_preflight.py"
BASE_ROOT="${TAJ20_ROOT:-$REPO_ROOT/runs/taj20-unified-runtime}"
CURRENT_FILE="$BASE_ROOT/CURRENT"
TAJ19_BASE="$REPO_ROOT/runs/taj19-broad-runtime"
MODE="${1:-status}"

fail() {
    echo "TAJ20_STATUS=BLOCKED"
    echo "REASON=$*"
    echo "HOLDOUT=CLOSED"
    echo "PROSPECTIVE=CLOSED"
    echo "PROMOTION=CLOSED"
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

resolve_taj19_campaign() {
    if [[ -n "${TAJ20_TAJ19_CAMPAIGN:-}" ]]; then
        [[ -d "$TAJ20_TAJ19_CAMPAIGN" ]] || fail "TAJ20_TAJ19_CAMPAIGN is not a directory: $TAJ20_TAJ19_CAMPAIGN"
        printf '%s\n' "$TAJ20_TAJ19_CAMPAIGN"
        return
    fi
    local pointer run_root campaign
    pointer="$TAJ19_BASE/CURRENT"
    [[ -f "$pointer" ]] || fail "TAJ-19 CURRENT pointer missing: $pointer"
    run_root="$(head -n 1 "$pointer")"
    campaign="$run_root/campaign"
    [[ -d "$campaign" ]] || fail "TAJ-19 campaign missing: $campaign"
    printf '%s\n' "$campaign"
}

new_run_root() {
    mkdir -p "$BASE_ROOT"
    local stamp root
    stamp="$(date -u +%Y%m%d-%H%M%S)"
    root="$BASE_ROOT/taj20-unified-$stamp"
    [[ ! -e "$root" ]] || fail "TAJ-20 run root already exists: $root"
    mkdir -p "$root"
    printf '%s\n' "$root" > "$CURRENT_FILE.tmp"
    mv "$CURRENT_FILE.tmp" "$CURRENT_FILE"
    printf '%s\n' "$root"
}

current_root() {
    [[ -f "$CURRENT_FILE" ]] || fail "no TAJ-20 current run exists"
    local root
    root="$(head -n 1 "$CURRENT_FILE")"
    [[ -n "$root" && -d "$root" ]] || fail "TAJ-20 current run root invalid: $root"
    printf '%s\n' "$root"
}

show_status() {
    echo "TAJ20_LAUNCHER=v1"
    echo "REPO_ROOT=$REPO_ROOT"
    echo "REPO_HEAD=$(git -C "$REPO_ROOT" rev-parse HEAD)"
    echo "EXPECTED_BROAD_IDENTITIES=174"
    echo "EXPECTED_PROBABILISTIC_IDENTITIES=76"
    echo "EXPECTED_UNIFIED_IDENTITIES=250"
    echo "EXPECTED_GAMES=6"
    echo "EXPECTED_REUSED_PAIRS=1044"
    echo "EXPECTED_INCREMENTAL_PAIRS=456"
    echo "EXPECTED_FINAL_PAIRS=1500"
    echo "HOLDOUT=CLOSED"
    echo "PROSPECTIVE=CLOSED"
    echo "PROMOTION=CLOSED"
    if [[ -f "$CURRENT_FILE" ]]; then
        local root
        root="$(head -n 1 "$CURRENT_FILE")"
        echo "CURRENT_RUN=$root"
        [[ -f "$root/preflight/PRECHECK_SUMMARY.json" ]] && echo "PREFLIGHT_EVIDENCE_PRESENT=YES" || echo "PREFLIGHT_EVIDENCE_PRESENT=NO"
    else
        echo "CURRENT_RUN=NONE"
        echo "PREFLIGHT_EVIDENCE_PRESENT=NO"
    fi
}

run_plan() {
    local root="$1"
    local identity_root="$root/identity-plan"
    local preflight_root="$root/preflight"
    local taj19_campaign
    taj19_campaign="$(resolve_taj19_campaign)"

    echo "[1/3]  33% derive live canonical 174 + 76 identity inventory"
    "${PY_CMD[@]}" "$PLANNER" --output "$identity_root"

    echo "[2/3]  66% verify immutable TAJ-19 reuse and freeze 456 incremental tasks"
    "${PY_CMD[@]}" "$PREFLIGHT" \
        --identity-root "$identity_root" \
        --taj19-campaign "$taj19_campaign" \
        --output "$preflight_root"

    echo "[3/3] 100% TAJ-20 plan gate finalized"
    echo "TAJ20_PLAN_ONLY=PASS"
    echo "TAJ20_RUN_ROOT=$root"
    echo "TAJ19_REUSE_CAMPAIGN=$taj19_campaign"
    echo "NEXT=probabilistic 76 x 6 incremental runtime certification"
}

case "$MODE" in
    status)
        show_status
        ;;
    plan)
        ROOT="$(new_run_root)"
        run_plan "$ROOT"
        ;;
    verify-plan)
        ROOT="$(current_root)"
        [[ -d "$ROOT/identity-plan" ]] || fail "identity plan missing in current run"
        [[ ! -e "$ROOT/preflight-reverify" ]] || fail "preflight-reverify already exists"
        TAJ19_CAMPAIGN="$(resolve_taj19_campaign)"
        "${PY_CMD[@]}" "$PREFLIGHT" \
            --identity-root "$ROOT/identity-plan" \
            --taj19-campaign "$TAJ19_CAMPAIGN" \
            --output "$ROOT/preflight-reverify"
        ;;
    *)
        echo "Usage: bash tools/taj20.sh {status|plan|verify-plan}"
        exit 2
        ;;
esac
