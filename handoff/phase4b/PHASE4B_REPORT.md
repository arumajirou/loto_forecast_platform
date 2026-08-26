# Phase 4B — GluonTS latest P6 lifecycle smoke

- status: **VERIFIED**
- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- runtime: `/mnt/e/env/ts/loto_forecast_platform/environments/gluonts-latest/.venv/bin/python`
- GluonTS: `0.17.0`
- Torch: `2.13.0`
- provider device policy: **CPU pinned** (`CUDA_VISIBLE_DEVICES` hidden by P6 campaign)
- model count: **9**
- lifecycle: FIT_SERIALIZE → separate-process LOAD_PREDICT
- data: deterministic P6 certification fixture; **not an accuracy-ranking dataset**
- final Hit@±1/MAE/MSE/RMSE comparison remains Phase 6 work

## Critical checks

- campaign_returncode_zero: `True`
- campaign_status_verified: `True`
- nine_models_present: `True`
- all_model_statuses_verified: `True`
- fit_reload_present_all: `True`
- fit_required_checks_pass_all: `True`
- reload_required_checks_pass_all: `True`
- provider_cpu_device_pass_all: `True`
- separate_process_reload_all: `True`
- all_critical_checks_pass: `True`

## Models

- `DeepNPTSEstimator`: `VERIFIED` (fit pid=3628950, reload pid=3629064)
- `DeepAREstimator`: `VERIFIED` (fit pid=3629135, reload pid=3629234)
- `TiDEEstimator`: `VERIFIED` (fit pid=3629309, reload pid=3629413)
- `SimpleFeedForwardEstimator`: `VERIFIED` (fit pid=3629592, reload pid=3629648)
- `TemporalFusionTransformerEstimator`: `VERIFIED` (fit pid=3629766, reload pid=3629822)
- `WaveNetEstimator`: `VERIFIED` (fit pid=3629937, reload pid=3630021)
- `DLinearEstimator`: `VERIFIED` (fit pid=3630114, reload pid=3630196)
- `PatchTSTEstimator`: `VERIFIED` (fit pid=3630278, reload pid=3630385)
- `LagTSTEstimator`: `VERIFIED` (fit pid=3630479, reload pid=3630556)

## Interpretation

This phase certifies the repository's current GluonTS P6 CPU contract on the existing latest runtime. Torch CUDA availability outside the provider process is provenance only and is not counted as GluonTS GPU execution.
