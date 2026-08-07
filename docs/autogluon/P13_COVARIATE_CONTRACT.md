# AutoGluon P13 External Covariate Contract

Status: `PARTIALLY_VERIFIED / CONTRACT_AND_FAKE_RUNTIME_PASS / REAL_RUNTIME_PENDING`

## Scope

P13 connects the protocol-v2 request to AutoGluon TimeSeries 1.5.0 external-feature inputs
without changing the shared worker, shared catalog, root dependency files, or workflows.

Supported request roles:

- known future covariates declared by `predictor.known_covariates_names`;
- past covariates declared by `covariates.past_covariates_names`;
- per-position static features declared by `covariates.static_feature_names` and supplied in
  `covariates.static_features`;
- global future-known rows supplied once per `horizon_step` and expanded to every position
  series using the synthetic regular timeline.

AutoGluon documents known and past covariates as columns in the historical
`TimeSeriesDataFrame`. Future known values are passed through `predict(...,
known_covariates=...)`, while static features are attached through
`TimeSeriesDataFrame.from_data_frame(..., static_features_df=...)`.

Official references:

- https://auto.gluon.ai/stable/api/autogluon.timeseries.TimeSeriesPredictor.predict.html
- https://auto.gluon.ai/stable/tutorials/timeseries/forecasting-indepth.html
- https://auto.gluon.ai/stable/tutorials/timeseries/forecasting-model-zoo.html

## Fail-closed rules

The provider rejects the request before importing or running AutoGluon when:

- a feature name is invalid, reserved, duplicated, or assigned to multiple roles;
- a historical known or past covariate is missing;
- a feature changes Python scalar type across historical rows;
- a value is null, non-finite, empty, or a nested unsupported object;
- future-known rows do not exactly cover `1..horizon`;
- future-known rows contain past/static/unknown fields;
- static features do not contain exactly one row for every position item;
- static item IDs or schemas differ;
- a load request does not match the saved covariate schema or saved static-feature hash.

No sorting, imputation, deduplication, dtype coercion, future-value inference, or silent feature
dropping is performed.

## Artifact binding

Fit writes `loto_covariate_context_v2.json` alongside the existing provider context. It binds:

- known, past, and static feature names;
- historical feature scalar types;
- covariate schema SHA-256;
- static-feature values SHA-256.

The context is validated before the pickle-backed predictor load. Future-known values are not
bound to the training artifact because they legitimately change for each prediction horizon.

## Explicit limitations

- Future-known rows are currently global and repeated across position items; item-specific
  future-known values are not yet implemented.
- `covariate_regressor` configuration and model-capability policy are not yet implemented.
- A model appearing in the AutoGluon inventory does not prove that it supports a requested
  covariate role. Runtime model-by-model certification is still required.
- Real AutoGluon 1.5.0 fit, predict, save/load, CPU fallback, and GPU evidence have not run in
  this execution environment.

## Local verification

- P13 focused tests: **15 passed**;
- Python compileall: **PASS**;
- changed Python lines over 100 characters: **0**;
- real AutoGluon runtime: **BLOCKED_RUNTIME**;
- GitHub Actions: **CI_BLOCKED_PRE_RUN**.
