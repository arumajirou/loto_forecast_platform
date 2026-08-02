#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v uv >/dev/null 2>&1 || {
  echo "ERROR: uv is required: https://docs.astral.sh/uv/" >&2
  exit 1
}
if uv sync --extra dev; then
  uv run pytest tests/research_closure
  uv run loto-research --help >/dev/null
else
  echo "WARN: online dependency resolution unavailable; using current Python for smoke only" >&2
  PYTHONPATH="$ROOT" python -m pytest tests/research_closure
  PYTHONPATH="$ROOT" python -m src.research_closure.cli --help >/dev/null
fi

uv run ruff check \
  src/research_closure \
  tests/research_closure

uv run ruff format \
  --check \
  src/research_closure \
  tests/research_closure

uv run mypy \
  src/research_closure

echo "INSTALL_TESTS_STATIC_QUALITY=PASS"
