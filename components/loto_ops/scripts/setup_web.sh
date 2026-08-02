#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

retry() {
  local n=1
  local max=5
  local delay=3
  while true; do
    "$@" && return 0
    if [ "$n" -ge "$max" ]; then
      return 1
    fi
    echo "[setup-web] retry $n/$max failed: $*" >&2
    n=$((n + 1))
    sleep "$delay"
    delay=$((delay * 2))
  done
}

if [ ! -d .venv ]; then
  ./scripts/setup_uv.sh
fi

retry uv sync --no-dev --extra web
. .venv/bin/activate
python - <<'PYCHECK'
import streamlit, plotly
print("[setup-web] streamlit:", streamlit.__version__)
print("[setup-web] plotly:", plotly.__version__)
PYCHECK
printf '\nweb setup done\n'
