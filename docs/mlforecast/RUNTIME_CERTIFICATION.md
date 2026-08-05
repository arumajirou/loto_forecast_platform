# MLForecast 1.1.0 Runtime Certification

## Current status

`PYPI_DIGEST_VERIFIED / INSTALLED_RUNTIME_EXECUTION_PENDING`

The official PyPI release metadata identifies the frozen wheel as:

- filename: `mlforecast-1.1.0-py3-none-any.whl`
- upload time: `2026-07-10T00:52:25.071033Z`
- size: `261702` bytes
- SHA-256: `0043190f540510979c7709bb69267caa9ac325a11fa49298cf3425307200e748`

This digest is now part of the executable provenance contract. It does not by
itself certify an installed runtime. Formal success additionally requires the
exact wheel file and the dedicated certification command to complete.

## Certification command

```bash
mkdir -p artifacts/mlforecast-wheel
uv run --with pip python -m pip download \
  --no-deps \
  --only-binary=:all: \
  --dest artifacts/mlforecast-wheel \
  mlforecast==1.1.0

OMP_NUM_THREADS=1 \
MKL_NUM_THREADS=1 \
OPENBLAS_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 \
uv run --frozen --with artifacts/mlforecast-wheel/mlforecast-1.1.0-py3-none-any.whl -- \
  python -m loto.mlforecast.certify \
  --wheel artifacts/mlforecast-wheel/mlforecast-1.1.0-py3-none-any.whl \
  --output-root artifacts/mlforecast-runtime-certification \
  --seed 1 \
  --auto-trials 2
```

## Pass criteria

Formal status is `RUNTIME_CERTIFIED` only when all of the following pass:

1. wheel bytes match the frozen SHA-256;
2. wheel `METADATA` reports `Name: mlforecast` and `Version: 1.1.0`;
3. installed distribution reports exactly version 1.1.0;
4. Core Ridge fits and produces two finite one-step predictions;
5. Core Ridge save/load repeats the same predictions;
6. AutoRidge runs the requested seeded Optuna trials;
7. AutoRidge produces finite predictions and survives save/load;
8. process, CPU, thread, package, prediction, trial, model, manifest, and hash
   artifacts are written.

A skipped test, missing wheel, version mismatch, incomplete trial set,
non-finite output, shape mismatch, or save/load prediction mismatch is failure.

## Expected artifacts

```text
RUNTIME_CERTIFICATION.json
synthetic_panel.csv
core_ridge_predictions.csv
auto_ridge_predictions.csv
auto_ridge_trials.csv
models/core-ridge/**
models/auto-ridge/**
ARTIFACT_MANIFEST.json
SHA256SUMS
```

## Boundary

The current conversation execution environment cannot resolve the PyPI file
host, so the official wheel bytes could not be installed here. Repository tests
can validate the certification implementation, but installed-runtime success
must be produced in an environment with the frozen wheel and dependencies.
