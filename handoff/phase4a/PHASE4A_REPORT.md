# Phase 4A Darts GPU Smoke

- status: `FAILED`
- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- model: ``
- runtime: `/mnt/e/env/ts/loto_forecast_platform/environments/darts-torch/.venv/bin/python`
- real data: ``
- real data rows used: ``
- GPU PIDs: `[]`
- peak matching VRAM MiB: `0`
- response status: ``
- save/reload certified: `False`

## Certification boundary

VERIFIED requires provider exit zero, successful fit/predict, exact position×horizon output shape, finite output, Hit@±1/MAE/MSE/RMSE metrics, all configured baselines, successful save/reload prediction equality, and provider/descendant GPU PID + VRAM evidence.

## Error

`RuntimeError: REAL_DATA_NOT_FOUND: set LOTO_PHASE4_DATA to a CSV/Parquet with draw_no and n1..nN`
