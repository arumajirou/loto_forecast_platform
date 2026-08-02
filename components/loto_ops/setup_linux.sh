#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$ROOT/setup_linux.sh" "$ROOT/verify_installation.sh" "$ROOT/run_loto_ops.sh" 2>/dev/null || true
CONFIG="${LOTO_OPS_CONFIG:-$ROOT/configs/loto_ops.yaml}"
SHARED_ROOT="${LOTO_SHARED_MEMORY_ROOT:-$ROOT/shared-ai-memory}"

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11+ required; found {sys.version.split()[0]}")
print(f"Python: {sys.version.split()[0]}")
PY

mkdir -p "$ROOT/runs" "$ROOT/runtime/logs" "$SHARED_ROOT/handovers" "$SHARED_ROOT/skills"
cp -a "$ROOT/skills/." "$SHARED_ROOT/skills/"

cat > "$ROOT/.loto_ops_env" <<EOF
export LOTO_OPS_PROJECT="$ROOT"
export LOTO_OPS_CONFIG="$CONFIG"
export LOTO_OPS_RUNS_DIR="$ROOT/runs"
export LOTO_HANDOVER_DIR="$SHARED_ROOT/handovers"
export LOTO_SKILLS_DIR="$SHARED_ROOT/skills"
EOF

SYNC_OK=0
if command -v uv >/dev/null 2>&1; then
    echo "Running: uv sync --frozen --all-groups --extra web"
    if uv sync --frozen --all-groups --extra web; then
        SYNC_OK=1
    else
        echo "uv sync failed. Check network/package registry access and retry." >&2
    fi
else
    echo "uv is not installed. Install uv, then rerun this script." >&2
fi

if [[ "$SYNC_OK" -eq 1 ]]; then
    PYTHON="$ROOT/.venv/bin/python"
    PYTEST="$ROOT/.venv/bin/pytest"
else
    PYTHON="$(command -v python3)"
    PYTEST="$(command -v pytest || true)"
    export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

    "$PYTHON" - <<'PY'
required = [
    "numpy", "pandas", "sqlalchemy", "yaml", "joblib", "requests",
]
optional_for_full_pipeline = ["psycopg", "polars", "pyarrow"]
missing = []
for name in required:
    try:
        __import__(name)
    except Exception:
        missing.append(name)
if missing:
    raise SystemExit(
        "Base dependencies missing: " + ", ".join(missing) +
        ". Restore registry access and run `uv sync --frozen --all-groups --extra web`."
    )
missing_optional = []
for name in optional_for_full_pipeline:
    try:
        __import__(name)
    except Exception:
        missing_optional.append(name)
if missing_optional:
    print("WARNING: full pipeline dependencies missing: " + ", ".join(missing_optional))
PY
fi

export LOTO_OPS_PROJECT="$ROOT"
export LOTO_OPS_CONFIG="$CONFIG"
export LOTO_OPS_RUNS_DIR="$ROOT/runs"
export LOTO_HANDOVER_DIR="$SHARED_ROOT/handovers"
export LOTO_SKILLS_DIR="$SHARED_ROOT/skills"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON" -m compileall -q "$ROOT/src"
"$PYTHON" -m loto_ops.cli --help >/dev/null
"$PYTHON" -m loto_ops.cli --config "$CONFIG" run --dry-run

if [[ -n "$PYTEST" && -x "$PYTEST" ]]; then
    "$PYTEST" -q
elif command -v pytest >/dev/null 2>&1; then
    pytest -q
else
    echo "pytest not found; installation smoke checks passed, tests skipped." >&2
fi

cat <<EOF
SETUP PASS
Project: $ROOT
Config:  $CONFIG
Run:     $ROOT/run_loto_ops.sh --help
Dry-run: $ROOT/run_loto_ops.sh run --dry-run
EOF

echo
echo "Optional automation setup:"
echo "  $ROOT/scripts/configure_runtime.sh"
echo "  $ROOT/scripts/test_notifications.sh"
echo "  $ROOT/scripts/install_user_services.sh 06:30 8520"
echo "Or run all three after setup:"
echo "  $ROOT/install_automation.sh 06:30 8520"
