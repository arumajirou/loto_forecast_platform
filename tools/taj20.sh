#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel)"
PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"

RUNS_ROOT="${TAJ20_RUNS_ROOT:-$ROOT/runs/taj20-unified-runtime}"
TAJ19_ROOT="${TAJ19_CAMPAIGN_ROOT:-}"
SEED="${TAJ20_SEED:-1}"

usage() {
    cat <<'EOF'
Usage:
  bash tools/taj20.sh status
  bash tools/taj20.sh plan
  bash tools/taj20.sh run
  bash tools/taj20.sh verify <probabilistic-root> <identity-root> [output-root]

Environment:
  TAJ19_CAMPAIGN_ROOT  Required for verify; accepted TAJ-19 campaign root.
  TAJ20_RUNS_ROOT      Optional root for new TAJ-20 runs.
  TAJ20_SEED           Runtime-certification seed (default: 1).
EOF
}

new_id() {
    date +taj20-%Y%m%d-%H%M%S
}

status() {
    echo "ROOT=$ROOT"
    echo "HEAD=$(git -C "$ROOT" rev-parse HEAD)"
    echo "TAJ20_RUNS_ROOT=$RUNS_ROOT"
    echo "TAJ19_CAMPAIGN_ROOT=${TAJ19_ROOT:-UNSET}"
    echo "TAJ20_SEED=$SEED"
    echo "HOLDOUT=CLOSED"
    echo "PROSPECTIVE=CLOSED"
    echo "PROMOTION=CLOSED"
}

plan() {
    local run_id
    local out
    run_id="$(new_id)"
    out="$RUNS_ROOT/$run_id/plan"
    mkdir -p "$RUNS_ROOT"
    "$PYTHON" "$ROOT/scripts/plan_all_execution_identities.py" --output "$out/identity"
    "$PYTHON" "$ROOT/scripts/run_taj20_probabilistic_matrix.py" plan \
        --root "$out/probabilistic" \
        --campaign-id "$run_id" \
        --seed "$SEED"
    echo "TAJ20_PLAN_ROOT=$out"
}

run_campaign() {
    local run_id
    local out
    run_id="$(new_id)"
    out="$RUNS_ROOT/$run_id"
    mkdir -p "$RUNS_ROOT"
    "$PYTHON" "$ROOT/scripts/plan_all_execution_identities.py" --output "$out/identity"
    "$PYTHON" "$ROOT/scripts/run_taj20_probabilistic_matrix.py" run \
        --root "$out/probabilistic" \
        --campaign-id "$run_id" \
        --seed "$SEED"
    echo "TAJ20_PROBABILISTIC_ROOT=$out/probabilistic"
    echo "TAJ20_IDENTITY_ROOT=$out/identity"
    if [[ -n "$TAJ19_ROOT" ]]; then
        "$PYTHON" "$ROOT/tools/runtime_audit/taj20_acceptance.py" \
            --taj19-root "$TAJ19_ROOT" \
            --probabilistic-root "$out/probabilistic" \
            --identity-root "$out/identity" \
            --output "$out/unified-acceptance"
        echo "TAJ20_UNIFIED_ROOT=$out/unified-acceptance"
    else
        echo "TAJ20_UNIFIED_ACCEPTANCE=EXECUTION_PENDING"
        echo "REASON=TAJ19_CAMPAIGN_ROOT is not set"
    fi
}

verify() {
    local prob_root="${1:-}"
    local identity_root="${2:-}"
    local output_root="${3:-}"
    if [[ -z "$TAJ19_ROOT" || -z "$prob_root" || -z "$identity_root" ]]; then
        echo "BLOCKED: TAJ19_CAMPAIGN_ROOT, probabilistic-root, and identity-root are required" >&2
        usage >&2
        return 2
    fi
    if [[ -z "$output_root" ]]; then
        output_root="$(dirname "$prob_root")/unified-acceptance-$(date +%Y%m%d-%H%M%S)"
    fi
    "$PYTHON" "$ROOT/tools/runtime_audit/taj20_acceptance.py" \
        --taj19-root "$TAJ19_ROOT" \
        --probabilistic-root "$prob_root" \
        --identity-root "$identity_root" \
        --output "$output_root"
}

case "${1:-}" in
    status) status ;;
    plan) plan ;;
    run) run_campaign ;;
    verify) shift; verify "$@" ;;
    *) usage; exit 2 ;;
esac
