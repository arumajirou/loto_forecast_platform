# RUNBOOK

## Install and validate

```bash
uv run python apply_all_auto_campaign.py \
  --project /mnt/e/env/ts/loto_forecast_platform
cd /mnt/e/env/ts/loto_forecast_platform
uv sync --extra auto-campaign --extra dev
uv run ruff format src/loto/auto_campaign scripts/experiments tests/auto_campaign
uv run ruff check src/loto/auto_campaign scripts/experiments tests/auto_campaign
uv run mypy src/loto/auto_campaign
uv run pytest tests/auto_campaign -q
```

## P0 and plan

```bash
uv run loto-auto-campaign inventory
uv run loto-auto-campaign plan
```

## P1 smoke

```bash
OUT="artifacts/miniloto-all-auto/p1-smoke-$(date +%Y%m%d-%H%M%S)"
uv run loto-auto-campaign run --stage smoke --output "$OUT"
uv run loto-auto-campaign verify --run "$OUT"
```

## Full local campaign

```bash
bash scripts/experiments/start_local_all_neuralforecast_auto_campaign.sh
GROUP="$(cat artifacts/miniloto-all-auto/LATEST-campaign)"
uv run python scripts/experiments/monitor_all_neuralforecast_auto.py \
  --group "$GROUP" --interval 5
```

## Resume one stage

```bash
uv run loto-auto-campaign run --stage holdout \
  --output "$GROUP/p5-holdout" \
  --source-run "$GROUP/p3-validation-replay" \
  --resume
```

## Failure inspection

Read `failures.json`, `attempt_failures/`, `failed_attempts/`, task manifests,
and Trial manifests. OOM is retried at lower concurrency with the same config;
other errors are not silently retried or converted to CPU.
