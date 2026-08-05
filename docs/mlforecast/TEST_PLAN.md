# MLForecast test plan

## Local fast gates

1. `python -m compileall -q src tests`
2. focused pytest under `tests/mlforecast`
3. Ruff format and lint when the repository-pinned Ruff executable is available

## Unit coverage

- strict config validation;
- all eight AutoMLForecast model names;
- declarative Optuna search-space conversion;
- Hit@±1-first objective ordering;
- position-wise and all-position metrics;
- deterministic baseline generation;
- duplicate rejection;
- chronological Train/Holdout isolation.

## Integration coverage

GitHub CI must run the repository-wide Ruff checks, compileall, and full pytest suite. A runtime environment installed with `--extra mlforecast` must additionally execute:

- Core Ridge fit/predict/save/load/re-predict;
- AutoRidge two-trial smoke;
- finite output and exact shape checks;
- optional future-exogenous smoke;
- artifact manifest and SHA-256 verification.

## Formal campaign deferred gate

A later real-data campaign must use multiple seeds and report mean, variance, and worst seed for Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE. No best-seed-only promotion is permitted.
