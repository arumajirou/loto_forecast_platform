# AutoGluon TimeSeries Provider v2

Status: IMPLEMENTED_P4 / fake-runtime verified / real AutoGluon execution pending

## Supported operations

- `fit_predict_save`
- `load_predict`

The legacy schema-v1 route remains available for the existing common worker. Schema v2
is selected only when the request contains `schema_version: 2`.

## Execution modes

| Mode | Effective AutoGluon behavior |
|---|---|
| `preset_automl` | Uses `presets`; explicit `model_ids` and dictionary hyperparameters are rejected. |
| `explicit_single_model` | Converts one `model_id` to `hyperparameters={model_id: config}`. Presets and ensembles are disabled. |
| `explicit_multi_model` | Converts selected IDs to a model-keyed hyperparameter mapping. Ensemble use remains explicit. |
| `hpo_single_model` | Uses one selected model plus required `hyperparameter_tune_kwargs`; ensembles are disabled. |
| `zero_shot_foundation` | Deferred and rejected with `EXECUTION_MODE_NOT_IMPLEMENTED_P4`. |
| `fine_tune_foundation` | Deferred and rejected with `EXECUTION_MODE_NOT_IMPLEMENTED_P4`. |

## Fail-closed rules

- unknown model IDs are rejected against the pinned AutoGluon 1.5.0 source manifest;
- duplicate model IDs are rejected by the Pydantic contract;
- preset mode cannot hide an explicit model dictionary;
- explicit modes cannot combine with `excluded_model_types`;
- single-model modes cannot accept ensemble configuration;
- HPO arguments require `hpo_single_model`, and HPO mode requires tune configuration;
- P4 rejects covariates and static features rather than silently dropping them;
- fit refuses a non-empty artifact directory;
- load refuses a missing or empty artifact directory;
- item IDs, horizon length, row count, mean, quantiles, and finite values are validated.

## Persisted evidence

A successful execution writes these files inside the AutoGluon artifact directory:

- `loto_provider_context_v2.json`
- `loto_execution_plan_v2.json`
- `loto_timeline_mapping_v2.json`

The context includes request, execution-plan, source-order, timeline-mapping, and geometry
SHA-256 values. Runtime evidence remains `PARTIAL` until PID, device use, and VRAM are
measured by the later GPU-certification phase.

## Current boundary

The production common worker still emits schema v1 because
`src/loto/models/workers.py` is outside this branch's ownership. Activating schema v2 as
the default production route requires a separately approved shared-scope change.
