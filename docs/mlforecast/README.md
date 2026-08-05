# MLForecast / AutoMLForecast integration

**Implementation status:** `EXECUTED / LOCAL_UNIT_VERIFIED / GITHUB_CI_PENDING`

This subsystem adds a separate, leakage-safe execution path for MLForecast 1.1.0. It does not modify the NeuralForecast runtime-certification work in PR #43.

## Scope

- strict Pydantic configuration for the MLForecast constructor, `fit`, `predict`, and chronological cross-validation;
- eight official AutoMLForecast models;
- Optuna sampler selection with default `seed=1`;
- a Hit@±1-first optimization objective;
- chronological Train/Holdout separation;
- overall and position-wise Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE;
- random, fixed, mean, median, last-value, frequency, and seasonal-naive baselines;
- model save, load, re-predict, finite-value and prediction-equality certification;
- prospective prediction sealing with SHA-256 and an explicit `actual_known=false` contract;
- CSV/Parquet input and optional future exogenous input;
- artifact manifest and portable `SHA256SUMS`.

## Supported Core estimators

| ID | Estimator |
|---|---|
| `linear_regression` | `sklearn.linear_model.LinearRegression` |
| `ridge` | `sklearn.linear_model.Ridge` |
| `lasso` | `sklearn.linear_model.Lasso` |
| `elastic_net` | `sklearn.linear_model.ElasticNet` |
| `random_forest` | `sklearn.ensemble.RandomForestRegressor` |
| `lightgbm` | `lightgbm.LGBMRegressor` |
| `xgboost` | `xgboost.XGBRegressor` |
| `catboost` | `catboost.CatBoostRegressor` |

## Supported AutoMLForecast models

- `AutoLightGBM`
- `AutoXGBoost`
- `AutoCatboost`
- `AutoLinearRegression`
- `AutoRidge`
- `AutoLasso`
- `AutoElasticNet`
- `AutoRandomForest`

These are the eight classes exported by `mlforecast.auto` in MLForecast 1.1.0. AutoMLForecast uses Optuna; Ray is not presented as an AutoMLForecast backend.

## Installation

This dedicated PR intentionally does not modify the shared `pyproject.toml` or `uv.lock`.
Run against the required runtime version explicitly:

```bash
uv run \
  --with mlforecast==1.1.0 \
  --with 'optuna>=4,<5' \
  --with 'lightgbm>=4.5' \
  --with 'xgboost>=2.1' \
  --with 'catboost>=1.2' \
  python -m loto.mlforecast.cli --help
```

Repository-wide dependency pinning is `BLOCKED_SHARED_SCOPE` in this PR and must be handled by a separate integration change after explicit approval.

## Execution

Core example:

```bash
uv run --with mlforecast==1.1.0 python -m loto.mlforecast.cli \
  --data /absolute/path/panel.csv \
  --config configs/mlforecast/core.yaml
```

AutoMLForecast example:

```bash
uv run --with mlforecast==1.1.0 --with 'optuna>=4,<5' python -m loto.mlforecast.cli \
  --data /absolute/path/panel.csv \
  --config configs/mlforecast/auto.yaml
```

When historical data contains extra feature columns, holdout exogenous values are taken from the withheld rows. Prospective execution fails closed unless matching future exogenous rows are supplied:

```bash
uv run --with mlforecast==1.1.0 --with 'optuna>=4,<5' python -m loto.mlforecast.cli \
  --data /absolute/path/panel.parquet \
  --config configs/mlforecast/auto.yaml \
  --prospective-exogenous /absolute/path/future_exogenous.parquet
```

## Data contract

Required columns:

- `unique_id`: series identifier;
- `ds`: integer or timestamp index;
- `y`: finite target value.

Duplicate `(unique_id, ds)` rows, missing required values, non-finite targets, invalid ordering, and insufficient history are rejected. Raw input is copied into the run directory and is never overwritten.

## Evaluation contract

The last `holdout_size` rows of every series are withheld. No scaler, feature transform, estimator, or AutoMLForecast trial is fitted on those rows. The default AutoMLForecast objective minimizes:

```text
number_of_Hit@±1_misses + bounded_MAE_tiebreak
```

The bounded MAE term is always below one, so one fewer miss always dominates any MAE improvement.

## Artifacts

Each run creates `artifacts/mlforecast/<run-id>/` containing:

- `config.json`
- `input_panel.csv`
- `train.csv`
- `holdout.csv`
- `holdout_predictions.csv`
- `core_cv_predictions.csv` or `optuna_trials_<model>.csv`
- baseline prediction CSV files
- `metrics.csv`
- `position_metrics.csv`
- `model/`
- `prospective_predictions.csv`
- `prospective_seal.json`
- `run_report.json`
- `ARTIFACT_MANIFEST.json`
- `SHA256SUMS`

## Certification boundaries

This PR does not claim accuracy improvement, Holdout superiority, Prospective success, GPU acceleration, live MLflow/PostgreSQL persistence, or completion of a real-data eight-model campaign. Those claims require execution on the registered dataset and environment with multiple seeds.

## Official references

- MLForecast 1.1.0 release: https://pypi.org/project/mlforecast/1.1.0/
- MLForecast API: https://nixtlaverse.nixtla.io/mlforecast/forecast.html
- AutoMLForecast API: https://nixtlaverse.nixtla.io/mlforecast/auto.html
- Hyperparameter optimization: https://nixtlaverse.nixtla.io/mlforecast/docs/how-to-guides/hyperparameter_optimization.html
- Source repository: https://github.com/Nixtla/mlforecast
