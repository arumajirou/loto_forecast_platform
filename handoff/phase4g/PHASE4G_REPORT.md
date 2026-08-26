# Phase 4G — StatsForecast Python 3.13 CPU runtime smoke

- status: **VERIFIED**
- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- environment: `environments/statsforecast-py313`
- runtime: `/mnt/e/env/ts/loto_forecast_platform/environments/statsforecast-py313/.venv/bin/python`
- Python: `3.13.13`
- StatsForecast: `2.1.1`
- model: `Naive`
- execution contract: **CPU intended** (`CUDA_VISIBLE_DEVICES` empty)
- GPU model execution: **NOT CLAIMED**
- lifecycle: FIT → PREDICT → Python pickle → separate-process RELOAD → PREDICT
- fit PID: `3736490`
- reload PID: `3736553`
- data: exact Phase 4A verified 128-row real-data window
- evaluation: 127 train rows + final 1-row holdout
- ranking: **non-ranking runtime smoke**; formal multi-seed/time-split ranking remains Phase 6

## Critical checks

- fit_status_verified: `True`
- reload_status_verified: `True`
- statsforecast_version_fit: `True`
- statsforecast_version_reload: `True`
- model_identity_fit: `True`
- four_positions_fit: `True`
- four_positions_reload: `True`
- fit_shape_finite_all: `True`
- reload_shape_finite_all: `True`
- separate_process_reload: `True`
- prediction_equal_after_reload: `True`
- cpu_env_fit: `True`
- cpu_env_reload: `True`
- torch_not_imported_fit: `True`
- torch_not_imported_reload: `True`
- gpu_monitor_fit_healthy: `True`
- gpu_monitor_reload_healthy: `True`
- no_gpu_pid_fit: `True`
- no_gpu_pid_reload: `True`
- metrics_complete: `True`
- baselines_complete: `True`
- training_holdout_ordered: `True`
- all_critical_checks_pass: `True`

## Runtime-smoke metrics

- Hit@±1: `0.75`
- MAE: `1.25`
- MSE: `2.75`
- RMSE: `1.6583123951777`
- position Hit@±1: `[1.0, 1.0, 0.0, 1.0]`
- all-position Hit@±1: `0.0`

## Interpretation

This phase certifies the existing StatsForecast 2.1.1 Python 3.13 CPU runtime without dependency or lockfile mutation. The Naive model is used as a lifecycle representative. Metrics and baselines are smoke evidence only and are not Phase 6 ranking evidence.
