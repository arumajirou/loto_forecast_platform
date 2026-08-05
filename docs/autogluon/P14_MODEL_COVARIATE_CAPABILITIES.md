# AutoGluon P14 model/covariate capability gate

## Status

`PARTIALLY_VERIFIED / STATIC_CAPABILITY_GATE / REAL_RUNTIME_PENDING`

This phase prevents an external-covariate request from being treated as successful when the
selected AutoGluon model silently ignores one or more requested feature roles.

## Official AutoGluon 1.5.0 basis

Primary references:

- https://auto.gluon.ai/stable/tutorials/timeseries/forecasting-model-zoo.html
- https://auto.gluon.ai/stable/_modules/autogluon/timeseries/models/abstract/abstract_timeseries_model.html
- https://auto.gluon.ai/stable/_modules/autogluon/timeseries/models/chronos/chronos2.html
- https://auto.gluon.ai/stable/_modules/autogluon/timeseries/models/gluonts/models.html

The model-zoo summary declares native additional-feature support for the following families.
`PerStepTabular` is included from the AutoGluon tabular forecaster base-class capability flags
and its model description.

| Model ID | Known future | Past | Static |
|---|---:|---:|---:|
| DirectTabular | yes | no | yes |
| PerStepTabular | yes | no | yes |
| RecursiveTabular | yes | no | yes |
| DeepAR | yes | no | yes |
| PatchTST | yes | no | no |
| TemporalFusionTransformer | yes | yes | yes |
| TiDE | yes | no | yes |
| WaveNet | yes | no | yes |
| Chronos2 | yes | yes | no |

All other source-declared model IDs default to no native additional-feature support. This is a
fail-closed default, not a claim that future AutoGluon versions can never support them.

## Covariate regressor route

AutoGluon 1.5.0 exposes `covariate_regressor` values `LR`, `GBM`, `CAT`, `XGB`, and `RF`.
When explicitly configured for a model, it can provide a supported route for known covariates
and static features. It does not provide a route for past covariates.

Unknown values, search-space descriptors, booleans, and non-string values are rejected by the
P14 gate because the effective support route cannot be proven before training.

## Formal execution policy

External-covariate certification requires explicit model IDs.

- `preset_automl` is rejected because it may combine models that consume and ignore features.
- Every selected model must support every requested role.
- Multi-model runs fail if even one selected model lacks a requested role.
- `disable_known_covariates`, `disable_past_covariates`, and `disable_static_features` are
  interpreted as effective capability changes.
- A disabled known/static native route may be replaced by an explicit covariate regressor.
- A disabled or unsupported past route cannot be replaced by a covariate regressor.

## Artifact contract

Successful fit writes:

`loto_covariate_capability_v2.json`

The file records AutoGluon version, execution mode, selected models, requested roles, each
model/role route, configured regressor, and a canonical SHA-256. `load_predict` validates this
file before delegating to the pickle-backed AutoGluon loader.

The response metadata includes:

- `covariate_capability_decision`
- `covariate_capability_sha256`

The response artifacts include:

- `covariate_capability_context`

## Verification performed

- P14 capability and wrapper tests: 28 passed.
- P13 + P14 local regression set: 43 passed.
- Python compileall: PASS.
- lines over 100 characters in P14 changed Python files: 0.

## Remaining gates

This phase does not prove that any model successfully consumes covariates in the real
AutoGluon 1.5.0 runtime. Required next evidence includes model-by-model fit/predict/save/load,
observed model capability metadata, known/static/past ablations, Ruff, mypy, full pytest,
GitHub Actions, and CPU/GPU runtime evidence.
