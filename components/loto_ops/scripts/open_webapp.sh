#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8520}"
cd "$ROOT"
exec "$ROOT/run_loto_ops.sh" webapp --port "$PORT" --auto-port
