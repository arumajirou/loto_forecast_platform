#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
HELPER="$SCRIPT_DIR/runtime_audit/taj19_gpu_wait.py"
TAJ19="$SCRIPT_DIR/taj19.sh"
MODE="${1:-status}"

python_cmd() {
    if command -v uv >/dev/null 2>&1; then
        printf '%s\0' uv run --frozen python
    elif command -v python3 >/dev/null 2>&1; then
        printf '%s\0' python3
    else
        echo "TAJ19_GPU_STATUS=BLOCKED"
        echo "REASON=uv/python3 is required"
        exit 20
    fi
}

readarray -d '' -t PY_CMD < <(python_cmd)

case "$MODE" in
    status)
        "${PY_CMD[@]}" "$HELPER" status
        ;;
    wait)
        "${PY_CMD[@]}" "$HELPER" wait
        ;;
    wait-run)
        "${PY_CMD[@]}" "$HELPER" wait
        echo "GPU_READY_FOR_TAJ19=YES"
        exec bash "$TAJ19" run
        ;;
    *)
        echo "Usage: bash tools/taj19-gpu.sh {status|wait|wait-run}"
        exit 2
        ;;
esac
