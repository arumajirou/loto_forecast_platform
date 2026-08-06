# AutoTimeLLM Runtime Certification Adapter

## Status

```text
ADAPTER_IMPLEMENTED
TARGET_HOST_EXECUTION_NOT_PERFORMED
REAL_NEURALFORECAST_NOT_EXECUTED
REAL_LLM_SNAPSHOT_NOT_LOADED
CPU_SMOKE_NOT_EXECUTED
GPU_FORMAL_NOT_EXECUTED
ACCURACY_NOT_EVALUATED
NOT_REGISTERED
```

## Purpose

This stacked change adds the AutoTimeLLM-specific runtime adapter, isolated worker, CLI, and target-host
wrapper required to connect PR #126 to the provider-neutral runtime-certification SDK in PR #123.
It does not duplicate the common SDK and does not register AutoTimeLLM in the shared catalog or campaign.

## Dependency boundary

```text
PR #126 AutoTimeLLM contract/factory
        +
PR #123 provider-neutral runtime SDK
        |
        v
AutoTimeLLM runtime adapter and worker
```

The adapter imports `loto.runtime_certification` lazily. If the SDK is absent, execution fails with a
structured `RuntimeSDKUnavailableError`. This branch can therefore remain stacked on PR #126 without
copying provider-neutral contracts, subprocess execution, replay comparison, artifact sealing, or ZIP
verification.

## Runtime sequence

```text
strict request validation
→ immutable snapshot identity conversion
→ exact neuralforecast==3.2.0 package gate
→ isolated process run-a
→ deterministic synthetic input generation
→ PinnedTimeLLM load and fixed-config fit
→ predict
→ NeuralForecast save
→ NeuralForecast load
→ re-predict and bounded replay check
→ device/PID/VRAM evidence capture
→ isolated process run-b
→ provider-neutral two-process verification
→ CERTIFICATION_REPORT.json
→ complete SHA256SUMS
→ deterministic evidence ZIP and sidecar
```

The worker does not read project Raw, Train, Validation, OOF, Holdout, Prospective, actual, or prediction
artifacts. The deterministic synthetic series is used only for runtime lifecycle verification and cannot
be represented as forecasting-performance evidence.

## Request contract

`AutoTimeLLMRuntimeRequest` fixes:

- request schema version `1.0.0`;
- portable Run ID;
- complete PR #126 `PinnedLLMIdentity`;
- `CPU_SMOKE` with `requested_device=cpu`, or `GPU_FORMAL` with `requested_device=cuda`;
- exact `neuralforecast==3.2.0`;
- horizon, architecture profile, seed, bounded training steps, batch sizes and validation size;
- minimum history length derived from the selected architecture;
- precision policy;
- replay tolerance;
- subprocess timeout;
- absolute working directory.

CPU execution requires `precision=32-true`. `val_check_steps` cannot exceed `max_steps`. The request is
canonicalized and SHA-256 bound before process execution.

## Provider-specific semantics

The worker owns only AutoTimeLLM and NeuralForecast semantics:

- construction of `PinnedTimeLLM` from the exact immutable local snapshot;
- position-univariate direct forecast shape `[1, horizon]`;
- deterministic synthetic integer-indexed series;
- real NeuralForecast `fit`, `predict`, `save`, `load`, and second `predict` calls;
- prediction-column resolution and exact horizon enforcement;
- fitted parameter-device inspection;
- CUDA peak allocated/reserved memory;
- `nvidia-smi` provider PID, GPU UUID, and used-memory sample capture.

The common SDK remains responsible for package/snapshot verification, timeout and exit checks, output
shape and finite values, distinct-process replay, requested/effective device agreement, CPU fallback,
GPU PID release, artifact manifest, SHA256SUMS, deterministic ZIP, and runtime-status boundaries.

## CPU and GPU evidence

### CPU_SMOKE

Requires:

- requested and effective device both CPU;
- `cpu_fallback=false`;
- no GPU PID, UUID, VRAM, or external GPU samples;
- two distinct real worker processes;
- successful load, fit, predict, save, reload, and re-predict;
- finite `[1, horizon]` output;
- replay difference within the request tolerance.

### GPU_FORMAL

Requires all CPU lifecycle checks plus:

- CUDA lequested and available;
- fitted model parameter device is CUDA;
- provider GPU PID equals the worker PID;
- positive peak allocated or reserved VRAM;
- matching `nvidia-smi` PID and GPU UUID sample while the process is alive;
- provider PID absent from the GPU process list after process exit;
- no CPU fallback.

No fractional-GPU or parallel-GPU trial path is introduced. This is a direct fixed-configuration runtime
lane, not Ray HPO and not nested Ray.

## Commands

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

./scripts/run_auto_timellm_runtime_certification.sh \
  /absolute/path/to/runtime-request.json \
  /absolute/path/to/artifacts/auto-timellm-runtime/<run-id>
```

The output directory must be absent or empty. The wrapper uses the repository `uv` environment with the
`full` optional dependency set. PR #123 must be present in the checkout until it is merged into main.

## Outputs

```text
RUNTIME_REQUEST.json
CERTIFICATION_REPORT.json
SHA256SUMS
processes/run-a/WORKER_RESPONSE.json
processes/run-a/model_bundle/**
processes/run-b/WORKER_RESPONSE.json
processes/run-b/model_bundle/**
<output-root>.zip
<output-root>.zip.sha256
```

The evidence ZIP is outside the evidence directory and is verified by the common SDK.

## Explicit non-claims

This implementation does not prove:

- that NeuralForecast, Transformers, Ray, CUDA, or the LLM snapshot is installed on the target host;
- that a CPU or GPU runtime campaign has passed;
- that AutoTimeLLM can be registered in the common Auto Campaign;
- Hit@±1, MAE, MSE, RMSE, position or all-position performance;
- superiority over Random, fixed, mean, median, last, frequency, or statistical baselines;
- OOF, Holdout, Prospective, champion, promotion, or production readiness.
