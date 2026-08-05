# MLForecast / AutoMLForecast integration

**Status:** `PYPI_DIGEST_VERIFIED / LOCAL_CONTRACT_HARDENED / PORTABLE_BUNDLE_VERIFIER_VERIFIED / SOURCE_HANDOFF_VERIFIED / INSTALLED_RUNTIME_PENDING`

This subsystem adds a dedicated, leakage-safe MLForecast path. It is independent of PR #43 and changes only `src/loto/mlforecast`, `tests/mlforecast`, `configs/mlforecast`, and `docs/mlforecast`.

## Frozen upstream contract

| Field | Value |
|---|---|
| package | `mlforecast` |
| required version | `1.1.0` |
| tag | `v1.1.0` |
| commit | `a1609efddf8cf1a83510a50cd5487b66f32271c6` |
| wheel SHA-256 | `0043190f540510979c7709bb69267caa9ac325a11fa49298cf3425307200e748` |

Version `1.1.0` is the verified target. The runtime checks the installed distribution version and fails closed on any other version.

## Supported Core estimators

- `linear_regression`
- `ridge`
- `lasso`
- `elastic_net`
- `random_forest`
- `lightgbm`
- `xgboost`
- `catboost`

The configuration maps to the frozen 1.1.0 constructor and fit/CV APIs: lags, lag transforms, date features, target transforms, static features, known-future exogenous features, prediction intervals, fitting options, cross-validation, update, save, and load.

The verified 1.1.0 arguments `date_features_as_dummies`, `drop_auxiliary_columns`, `cache_train_df`, `horizon_features`, and `horizon_feature_templates` are mapped explicitly. Unknown keys are rejected.

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
  --with mlforecast==1.1.0 \
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
  --with mlforecast==1.1.0 \
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

1. exact `mlforecast==1.1.0`;
2. model save;
3. `MLForecast.load()`;
4. repeated prediction with identical keys and columns;
5. finite output;
6. equality within `rtol=1e-8`, `atol=1e-8`.

## Certification boundary

This implementation does not claim real-data accuracy improvement, Holdout superiority, Prospective success, GPU acceleration, live MLflow/PostgreSQL persistence, or completion of a multiple-seed campaign. Those remain execution tasks.

## Official sources

- https://pypi.org/project/mlforecast/1.1.0/
- https://github.com/Nixtla/mlforecast/tree/v1.1.0
- https://nixtlaverse.nixtla.io/mlforecast/forecast.html
- https://nixtlaverse.nixtla.io/mlforecast/auto.html

## Formal runtime certification

The certification command verifies the exact official wheel bytes, embedded
`METADATA`, installed version, Core Ridge and AutoRidge fit/predict lifecycles,
save/load prediction equality, finite outputs, Optuna trials, process/CPU
metadata, and artifact SHA-256 values.

Download the exact frozen wheel without changing the project lock file:

```bash
mkdir -p artifacts/mlforecast-wheel
uv run --with pip python -m pip download \
  --no-deps \
  --only-binary=:all: \
  --dest artifacts/mlforecast-wheel \
  mlforecast==1.1.0
```

Run the certification in an environment where MLForecast 1.1.0 and its runtime
dependencies are installed:

```bash
OMP_NUM_THREADS=1 \
MKL_NUM_THREADS=1 \
OPENBLAS_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 \
uv run --frozen --with artifacts/mlforecast-wheel/mlforecast-1.1.0-py3-none-any.whl -- \
  python -m loto.mlforecast.certify \
  --wheel artifacts/mlforecast-wheel/mlforecast-1.1.0-py3-none-any.whl \
  --output-root artifacts/mlforecast-runtime-certification \
  --seed 1 \
  --auto-trials 2
```

Formal success requires the printed status to be `RUNTIME_CERTIFIED`. The run
directory contains `RUNTIME_CERTIFICATION.json`, prediction CSVs, Optuna trial
records, saved model bundles, `ARTIFACT_MANIFEST.json`, and `SHA256SUMS`.

## Source handoff bundle

After the MLForecast scope is committed and clean, build a deterministic source handoff package:

```bash
bash docs/mlforecast/build_handoff_bundle.sh
```

The package contains the required documentation set, MLForecast source, tests, configurations, frozen provenance, read-only snapshots of `pyproject.toml` and `uv.lock`, `SOURCE_PROVENANCE.json`, `VERSION`, `ARTIFACT_MANIFEST.json`, and `SHA256SUMS`. The builder includes only Git-tracked files from the MLForecast scope and fails closed when the scope is dirty.

A received handoff package must be verified before use:

```bash
uv run --frozen -- \
  python -m loto.mlforecast.handoff \
  --verify \
  --zip /absolute/path/mlforecast-handoff-<SHA>.zip \
  --sha256 /absolute/path/mlforecast-handoff-<SHA>.zip.sha256
```

Formal success is `HANDOFF_VERIFIED`. This verifies source-package integrity only; it does not replace installed runtime certification.
