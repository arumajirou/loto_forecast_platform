#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
cd "$ROOT" || exit 1
ROOT="$(realpath "$PWD")"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE="$SERVICE_DIR/loto-ppl-api.service"
TEMPLATE="$ROOT/deploy/systemd/user/loto-ppl-api.service.in"
mkdir -p "$SERVICE_DIR"
if ! test -f "$ROOT/.env.ppl-api"; then
    uv run loto3 probabilistic api-token-create --root "$ROOT"
fi
UV_BIN="$(command -v uv)"
test -n "$UV_BIN" || { echo "ERROR: uv not found" >&2; exit 2; }
test -f "$TEMPLATE" || { echo "ERROR: missing $TEMPLATE" >&2; exit 2; }
python3 - "$TEMPLATE" "$SERVICE" "$ROOT" "$UV_BIN" <<'PY'
from pathlib import Path
import sys

template = Path(sys.argv[1]).read_text(encoding="utf-8")
output = (
    template.replace("@ROOT@", sys.argv[3])
    .replace("@UV@", sys.argv[4])
)
Path(sys.argv[2]).write_text(output, encoding="utf-8")
PY
systemctl --user daemon-reload
systemctl --user enable --now loto-ppl-api.service
systemctl --user --no-pager --full status loto-ppl-api.service || true
echo "SERVICE=$SERVICE"
echo "API=http://127.0.0.1:8765/docs"
