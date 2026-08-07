# Moirai 2.0 Runbook

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail
RUN_ID="moirai2-$(date -u +%Y%m%dT%H%M%SZ)"
LOG="/mnt/e/env/logs/${RUN_ID}.log"
trap 'rc=$?; echo "EXIT_CODE=${rc}" | tee -a "$LOG"; read -r -p "Press Enter to close..." _' EXIT
uv lock --project environments/moirai2-supported-py311 2>&1 | tee -a "$LOG"
uv sync --project environments/moirai2-supported-py311 --frozen 2>&1 | tee -a "$LOG"
PYTHONPATH=src uv run pytest -q tests/adapters/moirai2 tests/moirai2_campaign 2>&1 | tee -a "$LOG"
```

Use tmux for real model and GPU certification. Record requested/effective device, PID, GPU UUID,
VRAM before/peak/after, output shape, all quantiles, and CPU fallback. Do not run Holdout or
Prospective in this increment.
