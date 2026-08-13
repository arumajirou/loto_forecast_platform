# LightGBM GPU / CUDA build certification

This runbook certifies the **installed LightGBM build** before the Broad scheduler is
allowed to route LightGBM models into a GPU lane.

## Why this gate exists

LightGBM has two distinct accelerator implementations on Linux:

- `device_type="gpu"`: the OpenCL GPU implementation;
- `device_type="cuda"`: the separate CUDA implementation for NVIDIA GPUs.

The CUDA implementation requires a LightGBM build compiled with `USE_CUDA=ON`. Merely
installing the repository's `full` extra (`lightgbm>=4.5`) does not prove that the resolved
wheel or local library contains CUDA support.

The repository therefore keeps `lightgbm-classifier` and `lightgbm-position` CPU-routed
until this probe produces retained runtime evidence.

## Probe

```bash
uv sync --extra dev --extra full --frozen
uv run python scripts/probe_lightgbm_gpu_build.py \
  --output artifacts/lightgbm-gpu-certification/$(date +%Y%m%d-%H%M%S) \
  --device-type auto \
  --rows 20000 \
  --features 64 \
  --rounds 200 \
  --seed 1
```

`auto` tries CUDA first and OpenCL GPU second.

## Acceptance criteria

A backend is `VERIFIED` only when all of the following are true:

1. LightGBM classifier construction, fit, and finite probability prediction succeed;
2. LightGBM regressor construction, fit, and finite prediction succeed;
3. the requested LightGBM `device_type` is the accelerator backend under test;
4. external NVIDIA telemetry records positive GPU utilization or a meaningful VRAM
   increase during the fit;
5. `CERTIFICATION.json` and `SHA256SUMS` are retained.

The probe fails closed when no NVIDIA GPU is visible, when the build rejects both
accelerator backends, or when model execution succeeds without external GPU activity.

## Status interpretation

- `VERIFIED`: the selected installed backend is eligible for a later routing PR;
- `UNSUPPORTED_BUILD_OR_RUNTIME`: the current installed LightGBM cannot execute either
  requested GPU backend;
- `INCONCLUSIVE`: fit completed but external GPU activity was not demonstrated;
- `BLOCKED_NO_NVIDIA_GPU`: no NVIDIA GPU telemetry source was available.

Certification does **not** change Holdout, Prospective, promotion, model identity, or the
Broad catalog denominator. A later explicit routing change is required after evidence is
reviewed.

## Upstream build contract

Current LightGBM documentation describes Linux CUDA builds with `-DUSE_CUDA=ON` and the
OpenCL GPU implementation with `-DUSE_GPU=ON`. The CUDA implementation uses
`device_type="cuda"`; the OpenCL implementation uses `device_type="gpu"`.
