# Darts runtime preflight

## Purpose

This stacked increment starts after the P1-P12 contract and handoff package. It does not
change Draft PR #47. Its purpose is to prove that a local environment is ready before a
real Darts campaign is allowed to start.

Official Darts 0.46.1 guidance separates the `darts`, `darts[torch]`, and
`darts[notorch]` installations. The target repository uses isolated notorch and torch
projects so optional dependencies and CUDA behavior cannot silently contaminate one
another.

## Profiles

### notorch

The notorch profile requires:

- Python 3.11 through 3.13;
- `darts==0.46.1`;
- a committed `environments/darts-notorch/uv.lock`;
- imports for Darts, StatsForecast, LightGBM, XGBoost, and CatBoost;
- all required local, regression, ensemble, and conformal model exports;
- CPU smoke plans for `NaiveMean` and `LinearRegressionModel`.

### torch

The torch profile requires:

- Python 3.11 through 3.13;
- `darts==0.46.1` and `torch==2.9.1`;
- a committed `environments/darts-torch/uv.lock`;
- Torch, Lightning, Hugging Face Hub, and safetensors imports;
- all ten P7 Torch models and all four P8 Foundation model exports;
- successful CUDA tensor allocation and synchronization;
- the current process PID in `nvidia-smi`;
- no CPU fallback;
- a GPU smoke plan for `NLinearModel`.

The `tirex` import is optional at preflight level. TiRex execution remains blocked until
its license, dependency, immutable revision, and local artifact requirements are met.

## Result classes

- `PASS`: every required check passed.
- `BLOCKED`: a required package, lockfile, import, or CUDA facility is unavailable.
- `FAIL`: an installed runtime violates the expected version, API, export, or evidence.
- `SKIPPED`: an optional check is unavailable and does not change the overall status.

A campaign can start only when the selected profile returns `PASS`.

## Commands

Generate the environment lock and sync it before running preflight:

```bash
uv lock --project environments/darts-notorch --python 3.13
uv sync --project environments/darts-notorch --frozen

uv lock --project environments/darts-torch --python 3.13
uv sync --project environments/darts-torch --frozen
```

Run the profiles:

```bash
uv run --project environments/darts-notorch \
  python scripts/run_darts_runtime_preflight.py \
  --profile configs/darts_campaign/runtime_preflight_notorch.yaml \
  --repository-root . \
  --output artifacts/darts-runtime-preflight/notorch.json

uv run --project environments/darts-torch \
  python scripts/run_darts_runtime_preflight.py \
  --profile configs/darts_campaign/runtime_preflight_torch.yaml \
  --repository-root . \
  --output artifacts/darts-runtime-preflight/torch.json
```

Exit codes are `0` for PASS, `1` for FAIL, and `2` for BLOCKED.

## Evidence

Each report stores:

- exact package versions;
- import and model-export results;
- lockfile size and SHA-256;
- Python executable, version, process ID, and platform;
- CUDA device count, current device, device name, tensor device;
- allocated and reserved CUDA memory;
- current PID and used memory from `nvidia-smi`;
- canonical report SHA-256.

No network access or model download is permitted by these profiles.
