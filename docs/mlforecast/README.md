# MLForecast / AutoMLForecast integration

**Status:** `IMPLEMENTED / LOCAL_CONTRACT_VERIFIED / REAL_RUNTIME_PENDING`

This subsystem adds a dedicated, leakage-safe MLForecast path. It is independent of PR #43 and changes only `src/loto/mlforecast`, `tests/mlforecast`, `configs/mlforecast`, and `docs/mlforecast`.

## Frozen upstream contract

| Field | Value |
|---|---|
| package | `mlforecast` |
| required version | `1.0.31` |
| tag | `v1.0.31` |
| commit | `c8f8b6d25184dcbed2454e185a92f3f8ef2e17e8` |
| wheel SHA-256 | `941c4623f3440e0c3fa63db9df0a9ad198045cdb04bd624c8188edd11c74a441` |

Version `1.1.0` is not part of this contract. The runtime checks the installed distribution version and fails closed unless it is exactly `1.0.31`.

## Supported Core estimators

- `linear_regression`
- `ridge`
- `lasso`
- `elastic_net`
- `random_forest`
- `lightgbm`
- `xgboost`
- `catboost`

The configuration maps to the frozen 1.0.31 constructor and fit/CV APIs: lags, lag transforms, date features, target transforms, static features, known-future exogenous features, prediction intervals, fitting options, cross-validation, update, save, and load.

Arguments not present in 1.0.31, including `date_features_as_dummies`, `drop_auxiliary_columns`, and `cache_train_df`, are rejected by the strict Pydantic schema rather than silently ignored.

## Supported AutoMLForecast models

- `AutoLightGBM`
- `AutoXGBoost`
- `AutoCatboost`
- `AutoLinearRegression`
- `AutoRidge`
- `AutoLasso`
- `AutoElasticNet`
- `AutoRandomForest`

AutoMLForecast uses Optuna. The default sampler is multivariate TPE with `seed=1`. Random, QMC, and CMA-ES samplers and declarative integer, float, and categorical search spaces are supported.

## Leakage-safe feature contract

Every non-key input column must be classified as exactly one of:

- `static_features`: constant within each series;
- `known_future_features`: values known for Holdout and Prospective timestamps;
- `weight_col`: non-negative finite sample weight.

Unclassified columns, changing static values, missing future rows, duplicate keys, and out-of-order input fail closed. Passing `static_features=[]` is intentional: it prevents MLForecast from treating all extra columns as static by default.

## Evaluation

- chronological per-series Train/Holdout split;
- Hit@±1 as the primary AutoML objective;
- bounded MAE tie-breaker that cannot outweigh one fewer Hit@±1 miss;
- Hit@±1, position-wise Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE;
- Random, fixed, mean, median, last-value, frequency, and seasonal-naive baselines;
- no best-seed-only promotion claim.

## Execution

The PR intentionally does not edit shared dependency files. Run the dedicated module with the frozen version:

```bash
uv run \
  --with mlforecast==1.0.31 \
  --with 'lightgbm>=4.6' \
  --with xgboost \
  --with catboost \
  python -m loto.mlforecast.cli \
  --data /absolute/path/panel.csv \
  --config configs/mlforecast/core.yaml
```

Auto mode:

```bash
uv run \
  --with mlforecast==1.0.31 \
  --with 'lightgbm>=4.6' \
  --with xgboost \
  --with catboost \
  python -m loto.mlforecast.cli \
  --data /absolute/path/panel.csv \
  --config configs/mlforecast/auto.yaml
```

When `known_future_features` is non-empty, pass exact future keys and values:

```bash
--prospective-exogenous /absolute/path/future_exogenous.parquet
```

## Artifacts and certification

Each run stores the raw source copy, canonical input, Train/Holdout, configuration, CV or Optuna trials, predictions, metrics, model bundles, environment package versions, prospective seal, artifact manifest, and portable SHA-256 sums.

Runtime certification requires:

1. exact `mlforecast==1.0.31`;
2. model save;
3. `MLForecast.load()`;
4. repeated prediction with identical keys and columns;
5. finite output;
6. equality within `rtol=1e-8`, `atol=1e-8`.

## Certification boundary

This implementation does not claim real-data accuracy improvement, Holdout superiority, Prospective success, GPU acceleration, live MLflow/PostgreSQL persistence, or completion of a multiple-seed campaign. Those remain execution tasks.

## Official sources

- https://pypi.org/project/mlforecast/1.0.31/
- https://github.com/Nixtla/mlforecast/tree/v1.0.31
- https://nixtlaverse.nixtla.io/mlforecast/forecast.html
- https://nixtlaverse.nixtla.io/mlforecast/auto.html
