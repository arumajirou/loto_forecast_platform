#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -d src/loto/data ]] || ./tools/restore_missing_data_sources.sh
command -v uv >/dev/null 2>&1 || { echo 'uv is required'; exit 2; }
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$ROOT/.venv-local-verify}"
uv sync --frozen --all-extras --all-groups
uv run python -c 'import loto; print("PASS: loto import")'
echo "environment=$UV_PROJECT_ENVIRONMENT"
