#!/usr/bin/env bash
# Open a new interactive bash shell with loto_ops_pipeline activated.
# Usage:
#   ./scripts/enter_env.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"
if [[ ! -d .venv ]]; then
  echo "[loto-ops] .venv が見つかりません。先に ./scripts/setup_uv.sh を実行します。"
  ./scripts/setup_uv.sh
fi
exec bash --rcfile <(printf 'source %q\nPS1="(loto-ops) $PS1"\n' "$PROJECT_DIR/activate_env.sh") -i
