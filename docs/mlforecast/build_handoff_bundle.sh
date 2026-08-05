#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$ROOT"

OUTPUT_DIR="${1:-$ROOT/artifacts/mlforecast-handoff}"

uv run --frozen -- \
  python -m loto.mlforecast.handoff \
  --build \
  --repo-root "$ROOT" \
  --output-dir "$OUTPUT_DIR"

HEAD_SHA="$(git rev-parse HEAD)"
SHORT_SHA="${HEAD_SHA:0:12}"
ZIP="$OUTPUT_DIR/mlforecast-handoff-$SHORT_SHA.zip"
SIDECAR="$ZIP.sha256"

uv run --frozen -- \
  python -m loto.mlforecast.handoff \
  --verify \
  --zip "$ZIP" \
  --sha256 "$SIDECAR"

printf 'HANDOFF_ZIP=%s\n' "$ZIP"
printf 'HANDOFF_SHA256=%s\n' "$SIDECAR"
