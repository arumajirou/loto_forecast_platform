# Quickstart: KPI Lab

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail
uv sync --frozen --extra dev
uv run pytest -q tests/test_kpi_lab_minimal.py tests/test_kpi_lab_solver_contract.py
uv run loto-lab --help
```

Optional CP-SAT certification:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail
uv add --optional solver 'ortools>=9.10'
uv sync --frozen --extra dev --extra solver
uv run pytest -q tests/test_kpi_lab_solver_contract.py
```

Do not add the optional dependency on a protected branch without reviewing the lockfile
diff and dependency licenses.
