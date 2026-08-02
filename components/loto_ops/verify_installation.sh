#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SHARED_ROOT="${LOTO_SHARED_MEMORY_ROOT:-$ROOT/shared-ai-memory}"
export LOTO_OPS_PROJECT="$ROOT"
export LOTO_OPS_CONFIG="${LOTO_OPS_CONFIG:-$ROOT/configs/loto_ops.yaml}"
export LOTO_OPS_RUNS_DIR="${LOTO_OPS_RUNS_DIR:-$ROOT/runs}"
export LOTO_HANDOVER_DIR="${LOTO_HANDOVER_DIR:-$SHARED_ROOT/handovers}"
export LOTO_SKILLS_DIR="${LOTO_SKILLS_DIR:-$ROOT/skills}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export TERM="${TERM:-dumb}"
mkdir -p "$LOTO_OPS_RUNS_DIR" "$LOTO_HANDOVER_DIR"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"
    PT="$ROOT/.venv/bin/pytest"
else
    PY="$(command -v python3)"
    PT="$(command -v pytest)"
fi
"$PY" -m compileall -q "$ROOT/src" "$ROOT/tests"
for args in \
  "--help" \
  "run --help" \
  "preflight --help" \
  "run-all --help" \
  "run-all-fast --help" \
  "webapp --help" \
  "package --help" \
  "export-handover --help" \
  "import-handover --help"; do
    # Intentional word splitting: args is a fixed internal command list.
    # shellcheck disable=SC2086
    "$PY" -m loto_ops.cli $args >/dev/null
done
"$PT" -q
printf 'VERIFY PASS\n'
