# Database-backed NeuralForecast AutoModel campaign

## Purpose

`loto neuralforecast automodel-run` reads a complete database table, converts it to
NeuralForecast's `unique_id`, `ds`, `y` panel, and executes the registered AutoModel
catalog. The current catalog contains 36 AutoModels.

For Numbers4, `normalized_draws.d1` through `d4` become four independent series and
`draw_no` becomes the integer time index. This uses `freq=1`; it does not invent
calendar observations for weekends or holidays.

## Status and certification contract

A model is not runtime-certified merely because `fit()` and the first `predict()`
returned successfully. By default the database campaign performs these checks for
every selected model:

1. initial prediction values are finite;
2. the fitted state dictionary is present and finite;
3. the complete `NeuralForecast` bundle is saved with its dataset;
4. the bundle is reloaded through `NeuralForecast.load()`;
5. post-load inference succeeds;
6. pre-save and post-load prediction shapes match;
7. post-load predictions are finite and match within `rtol=1e-6`, `atol=1e-6`;
8. CPU/GPU runtime and `nvidia-smi` PID evidence are recorded;
9. when GPU execution was requested, absence of CUDA evidence is treated as CPU fallback
   and fails certification.

The legacy-compatible top-level `status` remains `SUCCEEDED`, `PARTIAL`, or `FAILED`.
Use `certification_status` for formal interpretation:

- `RUNTIME_CERTIFIED`: every successful model passed save/load/re-predict certification;
- `TRAIN_ONLY`: training succeeded but certification was explicitly disabled;
- `PARTIAL`: at least one model was certified and at least one model failed;
- `FAILED`: no model achieved certification.

The default random seed for this command is `1`. Formal comparisons still require
multiple model seeds in the all-AutoModel campaign.

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
training NeuralForecast models. The generated plan includes the runtime-certification
policy and required evidence.

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
`max_gpu_jobs` bounds simultaneous model training. Remaining models wait in the queue.
Nested GPU trial parallelism is fail-closed: `parallel_trials` must be `1` whenever
`gpus > 0`. Increase outer concurrency only through `workers` and `max_gpu_jobs`.

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
  --gpus 1 \
  --save-models
```

The runner creates a digit-sum parent series plus four bottom position series and
uses a 5 by 4 summing matrix.

## Artifacts

- `input_panel.csv`: exact model input;
- `campaign_plan.json`: database, panel hash, Core/Fit arguments, queue policy, and
  certification contract;
- `campaign_report.json`: campaign outcome plus `certification_status` and certified
  model count;
- `models/<model-id>/run_report.json`: per-model training and certification status;
- `models/<model-id>/predictions.csv`: raw and legal decoded predictions;
- `models/<model-id>/prediction_after_load.csv`: prediction frame produced after reload;
- `models/<model-id>/runtime_certification.json`: finite/state/device/PID and prediction
  comparison evidence;
- `models/<model-id>/neuralforecast/`: retained model bundle when `--save-models` is
  enabled. The bundle may be removed after successful verification when retention is
  disabled, while certification evidence remains.

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
