# Moirai 2.0 Verification Report

Status: `PARTIALLY_VERIFIED / P7_FAKE_RUNTIME_PASS / REAL_RUNTIME_PENDING`.

## P0-P6 evidence retained from PR #83

- focused pytest: `28 passed`;
- Python `compileall`: `PASS`;
- provider identity smoke: `PASS`;
- structured-file parsing, path audit, SHA-256 verification, and secret scan: `PASS`.

## P7 executed locally

- changed-scope and related regression pytest: `30 passed`;
- fake Torch/GluonTS/Uni2TS runner boundary: `PASS`;
- past-only matrix shape and native field: `PASS`;
- known-future history-plus-horizon shape and native field: `PASS`;
- ordered feature identity and SHA-256 evidence: `PASS`;
- calendar gap expansion: `PASS`;
- target/covariate and cross-group collision rejection: `PASS`;
- covariate-aware token-budget rejection: `PASS`;
- univariate target shape and `one_dim_target=true`: `PASS`;
- Python `compileall`: `PASS`;
- Python source lines over 100 characters: `0`.

## Not executed or certified

- Ruff and mypy were unavailable in the authoring environment;
- isolated lockfile resolution and frozen synchronization;
- real Uni2TS import, snapshot load, or predictor execution;
- real native covariate transform and observed-mask behavior;
- all-nine-quantile inference with covariates;
- separate-process reload and re-prediction;
- CUDA PID, UUID, VRAM, and no-fallback certification;
- full repository pytest or successful GitHub Actions steps;
- OOF, Holdout, Prospective, accuracy, baseline superiority, calibration, or fine-tuning.

The fake boundary verifies project-side field names, shapes, dimensions, and response evidence. It is
not represented as model-runtime certification.
