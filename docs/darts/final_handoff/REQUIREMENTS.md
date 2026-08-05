# Requirements

## Primary objective

Maximize `Hit@±1`, defined as the proportion of predictions whose absolute error from the
observed value is at most one. Always report MAE, MSE, RMSE, position-wise Hit@±1, and
all-position Hit@±1.

## Comparison requirements

Compare every eligible model against Random, fixed value, mean, median, latest value,
frequency, and statistical baselines. Retain Darts native, Darts wrapper, standalone provider,
AutoGluon, and direct Foundation execution tracks without counting the same underlying
algorithm twice in the algorithm ranking.

## Time-series isolation

Split data chronologically into Train, Validation, Holdout, and Prospective partitions. Fit
scalers, encoders, feature selection, and hyperparameter optimization inside Train only.
Reject duplicate timestamps, missing values, order violations, future target lags, future past
covariates, and target-column reuse as covariates.

## Reproducibility

Use identical data hashes, folds, seeds, positions, horizon, lags, covariates, and metrics for
cross-library comparison. Preserve per-seed metrics, mean, population variance, and worst
seed. Never adopt a model using only its best seed.

## Runtime success

A model is successful only after import, load, input validation, fit when required, inference,
output-shape validation, finite-value validation, device validation, and persistence replay.
GPU claims require an effective CUDA device, process PID, GPU PID, VRAM before/peak/after,
and no CPU fallback.

## Prospective prediction

Seal predictions before observations are known using SHA-256 and a timestamp. Preserve the
sealed prediction payload and verification result.

## Engineering

Use `uv`, `pyproject.toml`, `uv.lock`, `src`, and `tests`. Prefer Ruff, mypy, pytest,
pytest-cov, and Pydantic. Run focused tests first and full repository tests and CI only after
implementation and local smoke verification.

## Final artifact

The handoff ZIP must contain exactly the 12 required documents listed in
`ARTIFACT_MANIFEST.md`, with a verified `SHA256SUMS` file and deterministic ZIP metadata.
