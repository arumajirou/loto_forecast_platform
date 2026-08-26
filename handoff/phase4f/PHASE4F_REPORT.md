# Phase 4F — sktime core Python 3.13 CPU runtime smoke

- status: **VERIFIED**
- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- environment: `environments/sktime-core-py313`
- runtime: `/mnt/e/env/ts/loto_forecast_platform/environments/sktime-core-py313/.venv/bin/python`
- Python: `3.13.13`
- sktime: `1.0.1`
- model: `NaiveForecaster(strategy='last')`
- execution contract: **CPU intended** (`CUDA_VISIBLE_DEVICES` empty)
- GPU model execution: **NOT CLAIMED**
- lifecycle: FIT → PREDICT → Python pickle → separate-process RELOAD → PREDICT
- fit PID: `3703670`
- reload PID: `3703900`
- data: exact Phase 4A verified 128-row real-data window
- evaluation: 127 train rows + final 1-row holdout
- ranking: **non-ranking runtime smoke**; formal multi-seed/time-split ranking remains Phase 6

## Critical checks

- fit_status_verified: `True`
- reload_status_verified: `True`
- sktime_version_fit: `True`
- sktime_version_reload: `True`
- model_identity_fit: `True`
- strategy_fit: `True`
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

This phase certifies the existing sktime 1.0.1 classic Python 3.13 runtime without dependency or lockfile mutation. Metrics and baselines are retained only as smoke evidence and must not be promoted as Phase 6 ranking evidence.
