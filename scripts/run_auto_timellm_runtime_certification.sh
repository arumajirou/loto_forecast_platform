#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 /absolute/path/to/runtime-request.json /absolute/path/to/output-root" >&2
  exit 2
fi

REQUEST_PATH="$1"
OUTPUT_ROOT="$2"

if [[ "$REQUEST_PATH" != /* || "$OUTPUT_ROOT" != /* ]]; then
  echo "Both request and output paths must be absolute." >&2
  exit 2
fi

uv run --extra full python -m loto.neuralforecast.auto_timellm.certify \
  --request "$REQUEST_PATH" \
  --output-root "$OUTPUT_ROOT"
