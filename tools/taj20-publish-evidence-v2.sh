#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
BASE_ROOT="${TAJ20_ROOT:-$REPO_ROOT/runs/taj20-unified-runtime}"
CURRENT_FILE="$BASE_ROOT/CURRENT"
PUBLISHER="$SCRIPT_DIR/runtime_audit/taj20_publish_evidence_v2.py"

[[ -f "$CURRENT_FILE" ]] || {
    echo "TAJ20_EVIDENCE_PUBLICATION=BLOCKED"
    echo "REASON=no TAJ-20 current run exists"
    exit 20
}
RUN_ROOT="$(head -n 1 "$CURRENT_FILE")"
[[ -n "$RUN_ROOT" && -d "$RUN_ROOT" ]] || {
    echo "TAJ20_EVIDENCE_PUBLICATION=BLOCKED"
    echo "REASON=TAJ-20 current run root invalid: $RUN_ROOT"
    exit 20
}

BRANCH="evidence/taj20-runtime-$(basename "$RUN_ROOT")"
if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    BRANCH_TIP="$(git -C "$REPO_ROOT" rev-parse "refs/heads/$BRANCH")"
    MAIN_TIP="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    if git -C "$REPO_ROOT" merge-base --is-ancestor "$BRANCH_TIP" "$MAIN_TIP"; then
        git -C "$REPO_ROOT" branch -D "$BRANCH"
        echo "STALE_LOCAL_EVIDENCE_BRANCH_RECOVERED=YES"
    else
        echo "TAJ20_EVIDENCE_PUBLICATION=BLOCKED"
        echo "REASON=stale local evidence branch contains commits not in current main: $BRANCH"
        exit 20
    fi
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run --frozen python "$PUBLISHER" --repo-root "$REPO_ROOT" --run-root "$RUN_ROOT"
fi
exec python3 "$PUBLISHER" --repo-root "$REPO_ROOT" --run-root "$RUN_ROOT"
