# Database-backed NeuralForecast AutoModel campaign

## Purpose

`loto neuralforecast automodel-run` reads a complete database table, converts it to
NeuralForecast's `unique_id`, `ds`, `y` panel, and executes the registered AutoModel
catalog. The current catalog contains 36 AutoModels.

For Numbers4, `normalized_draws.d1` through `d4` become four independent series and
`draw_no` becomes the integer time index. This uses `freq=1`; it does not invent
calendar observations for weekends or holidays.

## Dry run

```bash
uv run loto neuralforecast automodel-run \
  --db-url /absolute/path/to/datasets.sqlite3 \
  --table normalized_draws \
  --game numbers4 \
  --output runs/numbers4-nf-auto-dry-run \
  --models all \
  --backend optuna \
  --workers 8 \
  --gpus 1 \
  --max-gpu-jobs 1 \
  --dry-run
```

The command validates the table and all model selections without importing or
training NeuralForecast models.

## Small runtime smoke

```bash
uv run loto neuralforecast automodel-run \
  --db-url /absolute/path/to/datasets.sqlite3 \
  --table normalized_draws \
  --game numbers4 \
  --output runs/numbers4-nf-auto-smoke \
  --models nf-auto-dlinear,nf-auto-nlinear \
  --model-config configs/neuralforecast/numbers4_automodel_smoke.json \
  --backend optuna \
  --num-samples 1 \
  --val-size 20 \
  --cpus 4 \
  --gpus 1 \
  --workers 8 \
  --max-gpu-jobs 1 \
  --local-scaler-type robust \
  --local-static-scaler-type standard \
  --save-models
```

With a GPU campaign, requested workers remain visible in the plan while
`max_gpu_jobs` bounds simultaneous GPU training. Remaining models wait in the queue.

## Full campaign

```bash
uv run loto neuralforecast automodel-run \
  --db-url /absolute/path/to/datasets.sqlite3 \
  --table normalized_draws \
  --game numbers4 \
  --output runs/numbers4-nf-auto-all \
  --models all \
  --backend optuna \
  --num-samples 10 \
  --val-size 50 \
  --cpus 8 \
  --gpus 1 \
  --workers 8 \
  --max-gpu-jobs 1 \
  --save-models
```

`AutoHINT` is the exception: NeuralForecast 3.2.0 supports it only with Ray and a
hierarchical summing matrix. In an `all` campaign the runner automatically overrides
only AutoHINT to Ray. It can also be run separately:

```bash
uv run loto neuralforecast automodel-run \
  --db-url /absolute/path/to/datasets.sqlite3 \
  --table normalized_draws \
  --game numbers4 \
  --output runs/numbers4-nf-auto-hint \
  --models nf-auto-hint \
  --backend ray \
  --num-samples 10 \
  --val-size 50 \
  --cpus 8 \
  --gpus 1
```

The runner creates a digit-sum parent series plus four bottom position series and
uses a 5 by 4 summing matrix.

## Artifacts

- `input_panel.csv`: exact model input
- `campaign_plan.json`: database, panel hash, Core/Fit arguments and queue policy
- `campaign_report.json`: campaign outcome
- `models/<model-id>/run_report.json`: per-model status and error traceback
- `models/<model-id>/predictions.csv`: raw and legal decoded predictions
- `models/<model-id>/neuralforecast/`: saved model when `--save-models` is enabled

## Resilient run script

For the known Numbers4 SQLite bundle, run the staged wrapper:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
./scripts/run_numbers4_nf_automodels.sh dry-run
./scripts/run_numbers4_nf_automodels.sh smoke
./scripts/run_numbers4_nf_automodels.sh full
```

The wrapper saves stdout/stderr, the exit code, and campaign artifacts. Set
`LOTO_NO_WAIT=1` when it must run unattended.
