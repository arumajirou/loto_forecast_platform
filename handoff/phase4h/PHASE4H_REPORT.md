# Phase 4H — Toto 2.0 4M Python 3.12 CUDA runtime smoke

- status: **VERIFIED**
- source SHA: `0a13c287e0f0fcc8f983be3512654524dad18b2c`
- environment declaration: `environments/toto2-4m-py312`
- selected reusable runtime: `/mnt/e/env/ts/loto_forecast_platform/.runtime-envs/toto/bin/python`
- Python: `3.12.13`
- Torch: `2.13.0+cu130`
- Torch CUDA: `13.0`
- toto-2: `2.0.0`
- toto-models: `1.0.0`
- model: `Datadog/Toto-2.0-4m`
- pinned revision: `8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9`
- parameter count: `4144448`
- request device: `cuda`
- request dtype contract: `float32`
- lifecycle: CHECKPOINT LOAD → READY/GPU PID CAPTURE → FULL INFERENCE, repeated in two isolated processes
- provider PIDs: `[3808075, 3808613]`
- execution device: `cuda:0`
- model device: `cuda:0`
- output device: `cuda:0`
- peak VRAM bytes: `373293056`
- CPU fallback: `False`
- network model download: **disabled/offline**
- input: deterministic synthetic runtime fixture; no actual/holdout opened
- ranking: **non-ranking runtime smoke**; formal forecasting evaluation remains Phase 6

## Critical checks

- response_status_ok: `True`
- response_phase_predict: `True`
- model_identity_id: `True`
- model_identity_repo: `True`
- model_identity_revision: `True`
- model_identity_class: `True`
- model_identity_parameter_count: `True`
- requested_device_cuda: `True`
- execution_device_cuda: `True`
- model_device_cuda: `True`
- output_device_cuda: `True`
- positive_peak_vram: `True`
- external_gpu_pid_captured: `True`
- cpu_fallback_false: `True`
- runtime_scope_full_inference: `True`
- two_process_count: `True`
- two_process_distinct_pid: `True`
- two_process_gpu_evidence: `True`
- two_process_exact_replay: `True`
- snapshot_revision: `True`
- snapshot_weight_sha: `True`
- snapshot_weight_size: `True`
- input_shape: `True`
- output_shape: `True`
- output_finite: `True`
- quantile_monotonicity: `True`
- effective_native_shape: `True`
- effective_actuals_unused: `True`
- point_forecast_shape: `True`
- quantile_count: `True`
- response_values_finite: `True`
- native_first_shape: `True`
- native_second_shape: `True`
- native_finite: `True`
- native_exact_equal: `True`
- all_critical_checks_pass: `True`

## Interpretation

This phase certifies real Toto 2.0 4M checkpoint loading and CUDA inference in the Phase 3D-selected reusable Python 3.12 runtime. Availability or CUDA visibility alone is not accepted as success. Accuracy, lottery-domain quality, and argument-effectiveness ranking are intentionally outside this Phase 4 scope.
