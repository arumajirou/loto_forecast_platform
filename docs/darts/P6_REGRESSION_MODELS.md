# P6 Regression model contract

`PARTIALLY_VERIFIED / LOCAL_CONTRACT_VERIFIED / REAL_RUNTIME_PENDING`

## Model matrix

The P6 matrix retains these Darts identities:

- `LinearRegressionModel`
- `RandomForestModel`
- `LightGBMModel`
- `XGBModel`
- `CatBoostModel`
- `SKLearnModel`

A missing optional dependency remains a `DEPENDENCY_MISSING` row. It is never removed from
results or counted as an executable model.

## Fairness contract

Every candidate receives the same target lags, past/future covariate lags,
`output_chunk_length`, `output_chunk_shift`, `multi_models`, static-covariate policy,
horizon, seed, and chronological fold definition. Per-model arguments cannot override
these fields.

`SKLearnModel` requires a stable `estimator_id` and a runtime-injected estimator factory.
An opaque object is not serialized into configuration or provenance.

## Covariate safety

Covariate draw numbers must be integer, unique, increasing, and gap-free. Coverage must
extend through the forecast horizon, output shift, and maximum positive future-covariate
lag. Target position columns cannot be reused as covariates. Missing, non-finite, or short
coverage fails before model fitting.

Both position-local fitting and one global model over the full position sequence are
represented. Raw input frames are deep-copied and compared after execution.

## No-silent-drop rule

Constructor, fit, and predict arguments are checked against runtime signatures. Unknown
arguments fail the affected model and remain in its failure ledger. One model failure does
not terminate the remaining matrix.

## MLForecast parity

The parity payload fixes estimator identity, target and covariate lags, exogenous columns,
horizon, seed, and fold contract. A canonical SHA-256 changes when any comparison field
changes. This contract does not claim that an MLForecast comparison was executed.

## Certification boundary

Tests use fake TimeSeries, regression models, and estimator factories. Real Darts 0.46.1,
scikit-learn wrappers, LightGBM, XGBoost, CatBoost, OOF accuracy, and baseline superiority
remain pending.
