#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
cd "$ROOT"
if ! test -x "$ROOT/.venv/bin/python"; then
    echo "ERROR: project virtual environment not found: $ROOT/.venv" >&2
    exit 2
fi
uv pip install \
  --python "$ROOT/.venv/bin/python" \
  'fastapi>=0.115,<0.120' \
  'starlette<0.49' \
  'httpx>=0.27,<1' \
  'uvicorn>=0.34'
"$ROOT/.venv/bin/python" - <<'PY'
import fastapi
import httpx
import starlette
import uvicorn
print("API_DEPENDENCIES=PASS")
print("fastapi=", fastapi.__version__)
print("starlette=", starlette.__version__)
print("httpx=", httpx.__version__)
print("uvicorn=", uvicorn.__version__)
PY
