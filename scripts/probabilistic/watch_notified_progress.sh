#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
RUN_DIR="${2:-}"
cd "$ROOT"

if test -n "$RUN_DIR"; then
    exec uv run python scripts/probabilistic/progress_dashboard.py \
      --run-dir "$RUN_DIR" --interval 2
fi
exec uv run python scripts/probabilistic/progress_dashboard.py \
  --output-root "$ROOT/runs" --interval 2
