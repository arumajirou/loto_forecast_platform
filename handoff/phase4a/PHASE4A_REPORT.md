# Phase 4A Darts GPU Smoke

- status: `VERIFIED`
- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- model: `DLinearModel`
- runtime: `/mnt/e/env/ts/loto_forecast_platform/environments/darts-torch/.venv/bin/python`
- real data: `/mnt/e/env/ts/backups/loto-pre-consolidation-20260802-012717/loto_life_feature_pipeline/data/interim/bingo5_normalized.csv`
- real data rows used: `128`
- GPU PIDs: `[3585086]`
- peak matching VRAM MiB: `352`
- response status: `SUCCEEDED`
- save/reload certified: `True`

## Certification boundary

VERIFIED requires provider exit zero, successful fit/predict, exact position×horizon output shape, finite output, Hit@±1/MAE/MSE/RMSE metrics, all configured baselines, successful save/reload prediction equality, and provider/descendant GPU PID + VRAM evidence.
