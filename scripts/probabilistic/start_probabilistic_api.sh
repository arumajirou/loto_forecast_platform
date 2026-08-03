#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
cd "$ROOT"
if test -f "$ROOT/.env.ppl-notify"; then
    # shellcheck disable=SC1091
    source "$ROOT/.env.ppl-notify"
fi
if test -f "$ROOT/.env.ppl-api"; then
    # shellcheck disable=SC1091
    source "$ROOT/.env.ppl-api"
fi
: "${LOTO_PPL_API_TOKEN:?LOTO_PPL_API_TOKEN is not configured. Run create_api_token.sh first.}"
export LOTO_PPL_ROOT="$ROOT"
HOST="${LOTO_PPL_API_HOST:-127.0.0.1}"
PORT="${LOTO_PPL_API_PORT:-8765}"
if ! uv run python -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
    echo "ERROR: FastAPI/Uvicorn unavailable." >&2
    echo "Run: $ROOT/scripts/probabilistic/install_api_dependencies.sh $ROOT" >&2
    exit 2
fi
exec uv run uvicorn \
  loto.probabilistic.api:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers 1 \
  --access-log
