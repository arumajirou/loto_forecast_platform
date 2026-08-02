#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ENV="${LOTO_OPS_RUNTIME_ENV:-$HOME/.config/loto-ops/runtime.env}"

if [[ -f "$RUNTIME_ENV" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$RUNTIME_ENV"
    set +a
fi

SHARED_ROOT="${LOTO_SHARED_MEMORY_ROOT:-$ROOT/shared-ai-memory}"
export LOTO_OPS_PROJECT="$ROOT"
export LOTO_OPS_CONFIG="${LOTO_OPS_CONFIG:-$ROOT/configs/loto_ops.yaml}"
export LOTO_OPS_RUNS_DIR="${LOTO_OPS_RUNS_DIR:-$ROOT/runs}"
export LOTO_HANDOVER_DIR="${LOTO_HANDOVER_DIR:-$SHARED_ROOT/handovers}"
export LOTO_SKILLS_DIR="${LOTO_SKILLS_DIR:-$SHARED_ROOT/skills}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$LOTO_OPS_RUNS_DIR" "$LOTO_HANDOVER_DIR" "$LOTO_SKILLS_DIR"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"
else
    PY="$(command -v python3)"
fi

if [[ "$#" -eq 0 ]]; then
    set -- --help
fi

exec "$PY" -m loto_ops.cli --config "$LOTO_OPS_CONFIG" "$@"
