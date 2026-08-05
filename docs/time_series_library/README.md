# Time-Series-Library provider contract v1

## Status

`PARTIALLY_VERIFIED / CORE_CONTRACT_IMPLEMENTED / REAL_UPSTREAM_RUNTIME_PENDING`

This first increment creates an isolated process-boundary contract for
`thuml/Time-Series-Library` at revision
`4e938a1767106324dd753b2a44832bf870a0252e`.

## Scope

Included:

- fixed upstream provenance;
- isolated CPU dependency lane;
- strict Pydantic request and response schemas;
- draw-sequence `GameGeometry`;
- explicit Train, Validation, Holdout, and Prospective boundaries;
- training materialization that excludes Holdout and Prospective rows;
- AST-based runtime model inventory without importing optional dependencies;
- DLinear CPU construct, one-step fit, finite-state, save, process-exit, load,
  and re-predict contract;
- SHA-256 evidence for checkpoint, input, and predictions;
- fail-closed response status and exit code 2.

Excluded:

- root dependency changes;
- common worker or model catalog changes;
- Foundation Models and Mamba;
- GPU certification;
- real lottery Holdout or Prospective evaluation;
- accuracy or baseline-superiority claims.

## Why the upstream training loop is not reused directly

The upstream custom dataset computes a fixed 70/10/20 split internally and the
long-term training loop evaluates test loss during every epoch. The project requires
externally controlled chronological boundaries and no Holdout access during model
selection. The provider therefore defines its own split and artifact boundary.

## Core lane setup

```bash
cd /absolute/path/to/loto_forecast_platform/environments/tslib-core
uv sync

git clone https://github.com/thuml/Time-Series-Library \
  /absolute/path/to/Time-Series-Library
cd /absolute/path/to/Time-Series-Library
git checkout 4e938a1767106324dd753b2a44832bf870a0252e
```

No root `uv.lock` is modified.

## Provider operations

- `discover`
- `dlinear_fit_save`
- `dlinear_load_predict`
- `verify_roundtrip`

Example:

```bash
cd /absolute/path/to/loto_forecast_platform
uv run --project environments/tslib-core \
  python scripts/run_time_series_library_provider.py \
  --request /absolute/path/to/request.json \
  --response /absolute/path/to/response.json
```

## Certification boundary

A model listed by discovery is not runtime certified. DLinear is certified only after
both subprocesses and the comparison operation return `PASS`. GPU success additionally
requires a later lane with parameter, input, output, PID, VRAM, and no-CPU-fallback
evidence.
