#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
exec "$ROOT/scripts/probabilistic/run_fast_gpu_dashboard.sh" "$ROOT"
