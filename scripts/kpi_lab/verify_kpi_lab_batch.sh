#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${1:-$(pwd)}"
cd "$ROOT" || exit 1
PY="${KPI_LAB_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
fi
"$PY" -m pytest -q tests/test_kpi_lab_minimal.py tests/test_kpi_lab_solver_contract.py
"$PY" -m compileall -q src/loto/kpi_lab src/loto/combinatorics
if "$PY" -m ruff --version >/dev/null 2>&1; then
  "$PY" -m ruff check src/loto/kpi_lab src/loto/combinatorics \
    tests/test_kpi_lab_minimal.py tests/test_kpi_lab_solver_contract.py
else
  echo 'PARTIALLY_VERIFIED: ruff is not installed in the selected environment'
fi
