#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BUNDLE_TOOL="$SCRIPT_DIR/phase7_holdout_runner/evidence_bundle.py"
EVIDENCE_ROOT="${PHASE7_EVIDENCE_ROOT:-/mnt/e/env/ts/phase7_evidence}"
MODE="${1:-status}"

case "$MODE" in
    status)
        echo "PHASE7_EVIDENCE_TOOL=v1"
        echo "EVIDENCE_ROOT=$EVIDENCE_ROOT"
        if [[ -d "$EVIDENCE_ROOT" ]]; then
            echo "EVIDENCE_ROOT_PRESENT=YES"
        else
            echo "EVIDENCE_ROOT_PRESENT=NO"
        fi
        ;;
    import)
        BUNDLE="${2:-}"
        if [[ -z "$BUNDLE" ]]; then
            echo "Usage: bash tools/phase7-evidence.sh import /path/to/phase7-portable-evidence-v1-*.zip"
            exit 2
        fi
        command -v python3 >/dev/null 2>&1 || {
            echo "STATUS=BLOCKED"
            echo "REASON=python3 is required for evidence import"
            exit 20
        }
        echo "[1/3]  33% validate portable evidence bundle"
        echo "BUNDLE=$BUNDLE"
        echo "TARGET=$EVIDENCE_ROOT"
        echo "[2/3]  66% import without overwriting existing evidence"
        python3 "$BUNDLE_TOOL" import --bundle "$BUNDLE" --target "$EVIDENCE_ROOT"
        echo "[3/3] 100% evidence import complete"
        echo "NEXT=bash tools/phase7.sh holdout"
        ;;
    *)
        echo "Usage: bash tools/phase7-evidence.sh {status|import <bundle.zip>}"
        exit 2
        ;;
esac
