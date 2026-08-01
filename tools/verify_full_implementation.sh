#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$ROOT/.venv-local-verify}"
uv run ruff check src scripts tests
uv run python -m py_compile \
  src/loto/features/spec.py src/loto/features/registry.py \
  src/loto/features/point_in_time.py src/loto/models/forecast_input.py \
  src/loto/models/exogenous_adapters.py src/loto/analysis/contribution.py \
  scripts/analysis/aggregate_condition_contributions.py
uv run pytest -q
printf 'PASS: full verification\n'
