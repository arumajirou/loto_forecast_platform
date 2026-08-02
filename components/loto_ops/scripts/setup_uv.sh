#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

retry() {
  local n=1
  local max=3
  local delay=2
  while true; do
    "$@" && return 0
    if [ "$n" -ge "$max" ]; then
      return 1
    fi
    echo "[setup] retry $n/$max failed: $*" >&2
    n=$((n + 1))
    sleep "$delay"
    delay=$((delay * 2))
  done
}

if [ ! -d .venv ]; then
  if [ -n "${PYTHON_VERSION:-}" ]; then
    PY_FOR_VENV="$PYTHON_VERSION"
  elif uv python find 3.12 >/dev/null 2>&1; then
    PY_FOR_VENV="3.12"
  else
    PY_FOR_VENV="$(command -v python3)"
  fi
  echo "[setup] python for venv: $PY_FOR_VENV"
  retry uv venv --python "$PY_FOR_VENV"
fi

# CLI運用に必要な最小依存だけを同期します。
# Streamlit/Plotly は web extra に分離し、uvicorn等のネットワーク失敗でCLI全体が壊れないようにします。
if ! retry uv sync --no-dev; then
  echo "[setup] uv sync failed. Falling back to editable install without dependency resolution." >&2
  uv pip install -e . --no-deps
fi

# console script が無い場合でも python -m で確実に起動できるラッパーを作ります。
if [ ! -x .venv/bin/loto-ops ]; then
  cat > .venv/bin/loto-ops <<'EOS'
#!/usr/bin/env bash
PROJECT_ROOT="/mnt/e/env/ts/loto_ops"
if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PY="$VIRTUAL_ENV/bin/python"
else
  PY="$PROJECT_ROOT/.venv/bin/python"
fi
export PYTHONPATH="$PROJECT_ROOT/src:${PYTHONPATH:-}"
exec "$PY" -m loto_ops.cli "$@"
EOS
  chmod +x .venv/bin/loto-ops
fi

. .venv/bin/activate
python - <<'PYCHECK'
import importlib
required = ["numpy", "pandas", "polars", "pyarrow", "sqlalchemy", "psycopg", "yaml"]
missing = []
for name in required:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append(f"{name}: {exc}")
if missing:
    raise SystemExit("missing required deps:\n" + "\n".join(missing))
import loto_ops.cli
print("[setup] import loto_ops.cli: OK")
PYCHECK

printf '\nsetup done\n'
