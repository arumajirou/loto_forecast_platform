# REQUIREMENTS

## Scope

Implement a separate NeuralForecast all-AutoModel campaign without changing or
reclassifying the completed AutoTFT persistence pilot.

## Functional requirements

- Discover every runtime `neuralforecast.auto.__all__` class that is a
  `BaseAuto` subclass.
- Reject Auto-prefixed false positives and stop on API drift.
- Record all 17 `BaseAuto`, 4 `NeuralForecast`, and 11 `fit` arguments.
- Exercise Ray and Optuna where supported; record unsupported combinations.
- Catalog every model default configuration and domain.
- Cover all finite categories, numeric boundary/quantile/random representatives,
  and all factor pairs.
- Use U-Shared, U-Local, M-Joint, and H-HINT data tracks.
- Preserve chronological Train/Validation/Holdout/Prospective order.
- Run 5 Train-only expanding OOF folds and seeds 1, 42, and 2026.
- Rank by Validation Hit@±1 before MAE and RMSE.
- Persist every successful HPO trial and every selected model.
- Verify load, input, predict, output shape, finite values, CUDA evidence, GPU
  PID, VRAM, and no silent CPU fallback.
- Evaluate Hit@±1, position Hit@±1, all-position Hit@±1, exact hit, MAE, MSE,
  and RMSE against all declared baselines.
- Freeze Prospective predictions with UTC time and SHA-256 before actuals.
- Provide resumable stages and progress bars.

## Non-functional requirements

- Python package under `src/`, Pydantic contracts, Ruff, mypy, pytest.
- Raw input is read-only.
- Eight logical workers; GPU concurrency is 4/2/1 by resource profile.
- OOM retries retain the exact model configuration and lower concurrency only.
- Missing Spark execution is reported as `PARTIAL_API_COVERAGE`, never PASS.
- A model being importable is not a successful runtime certification.
