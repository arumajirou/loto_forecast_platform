# P12 cross-library comparison contract

## Scope

P12 compares these eight execution tracks without treating wrappers as new algorithms:

1. Darts native;
2. Darts NeuralForecast wrapper;
3. Darts StatsForecast wrapper;
4. standalone NeuralForecast;
5. standalone MLForecast;
6. standalone StatsForecast;
7. AutoGluon;
8. Foundation direct provider.

The implementation is a comparison and evidence contract. It does not claim that the
real providers were installed, executed, or shown to improve forecast accuracy.

## Fairness boundary

Every successful execution must use the same immutable comparison contract:

- raw and comparison data SHA-256 values;
- chronological Train, Validation, Holdout, and Prospective boundaries;
- fold IDs and multiple seeds;
- target positions and series layout;
- forecast horizon;
- target, past-covariate, and future-covariate lags;
- past, future, and static covariate columns;
- Train-only Scaler, Encoder, feature-selection, and HPO fitting;
- fold, feature, and code-contract SHA-256 values.

Formal comparison rejects positive target/past lags, target reuse as a covariate, missing
seed or fold coverage, duplicate forecast keys, incomplete position coverage, and
provider-specific prediction keys.

## Wrapper and base identity

Each execution stores both execution identity and base-algorithm identity. For example:

```text
execution_library=darts
wrapper_library=darts
base_library=neuralforecast
base_model=NHITS
```

A canonical algorithm key excludes the wrapper and includes the base library, base model,
immutable revision, estimator identity, and model-configuration SHA-256. Multiple wrappers
for the same key require exactly one canonical execution. Wrapper variants remain visible
for prediction and metric-delta analysis but contribute only one row to algorithm ranking.

This prevents double counting for Darts NeuralForecast/StatsForecast wrappers and for
Darts, AutoGluon, or direct-provider executions of the same Foundation model.

## Metrics and adoption gate

P12 retains:

- Hit@±1 as the primary metric;
- position Hit@±1;
- all-position Hit@±1;
- MAE, MSE, and RMSE;
- per-seed values;
- mean, population variance, and worst value across seeds.

Best-seed-only adoption is forbidden. A canonical execution becomes champion only when it
improves the strongest baseline mean Hit@±1 and does not regress the strongest baseline
worst-seed Hit@±1. Required baselines are Random, fixed, mean, median, last, frequency, and
statistical.

## Runtime and failure evidence

Every provider publishes package versions, config/code/data hashes, Git commit, runtime,
memory, requested/effective device, and formal forecast records. GPU success requires an
effective GPU plus process PID, GPU PID, and VRAM before/peak/after evidence. CPU fallback
cannot be recorded as a successful GPU execution.

One provider failure does not stop the matrix. Failed tracks remain in the report with
failure class and message, while only complete successful records enter formal metrics.
