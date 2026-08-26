# Phase 4D — Darts no-torch CPU lifecycle smoke

- status: **VERIFIED**
- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- environment: `environments/darts-notorch`
- runtime: `/mnt/e/env/ts/loto_forecast_platform/environments/darts-notorch/.venv/bin/python`
- Darts: `0.46.1`
- model: `NaiveDrift`
- formal runtime/device contract: `runtime=notorch`, `device=cpu`
- provider CUDA visibility: hidden (`CUDA_VISIBLE_DEVICES=""`)
- provider/descendant GPU PIDs observed: `[]`
- lifecycle: fit -> predict -> save -> load -> predict equality
- data: same verified historical source/window rule as Phase 4A
- metrics are smoke evidence only; final model ranking remains Phase 6
- dependency/lock files modified: **False**

## Critical checks

- process_exit_zero: `True`
- response_succeeded: `True`
- requested_runtime_notorch: `True`
- requested_device_cpu: `True`
- provider_cuda_hidden: `True`
- no_provider_gpu_pid_observed: `True`
- prediction_shape: `True`
- prediction_finite: `True`
- metrics_complete: `True`
- baselines_complete: `True`
- save_reload_certified: `True`
- all_critical_checks_pass: `True`
