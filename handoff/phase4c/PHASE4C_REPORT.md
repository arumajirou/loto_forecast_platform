# Phase 4C — GluonTS compat P6 lifecycle smoke

- status: **VERIFIED**
- local run id: `20260826-132838`
- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- environment: `environments/gluonts-compat`
- runtime Python: `3.13.13`
- GluonTS: `0.16.3`
- Torch: `2.9.1`
- Torch CUDA build visible outside provider: `12.8`
- formal P6 device policy: **CPU pinned**
- GPU model execution: **NOT CLAIMED**
- model count: **9**
- lifecycle: FIT_SERIALIZE → separate-process LOAD_PREDICT
- dataset: deterministic certification fixture; **not an accuracy-ranking dataset**
- Phase 6 remains responsible for Hit@±1 / MAE / MSE / RMSE ranking

## Critical checks

- all_critical_checks_pass: `True`
- all_model_statuses_verified: `True`
- campaign_returncode_zero: `True`
- campaign_status_verified: `True`
- device_cpu_contract_all: `True`
- fit_checks_pass_all: `True`
- fit_reload_present_all: `True`
- model_order_exact: `True`
- nine_models_present: `True`
- reload_checks_pass_all: `True`
- separate_process_reload_all: `True`

## Models

- `DeepNPTSEstimator`: `VERIFIED` (fit pid=3640589, reload pid=3640697)
- `DeepAREstimator`: `VERIFIED` (fit pid=3640748, reload pid=3640842)
- `TiDEEstimator`: `VERIFIED` (fit pid=3640911, reload pid=3640996)
- `SimpleFeedForwardEstimator`: `VERIFIED` (fit pid=3641048, reload pid=3641137)
- `TemporalFusionTransformerEstimator`: `VERIFIED` (fit pid=3641190, reload pid=3641297)
- `WaveNetEstimator`: `VERIFIED` (fit pid=3641351, reload pid=3641463)
- `DLinearEstimator`: `VERIFIED` (fit pid=3641600, reload pid=3641687)
- `PatchTSTEstimator`: `VERIFIED` (fit pid=3641757, reload pid=3641828)
- `LagTSTEstimator`: `VERIFIED` (fit pid=3641911, reload pid=3641986)

## Interpretation

Phase 4C certifies the existing GluonTS 0.16.3 compatibility lane against the repository P6 CPU lifecycle contract. CUDA availability in the outer runtime is provenance only and is not evidence of model GPU execution.
