# Moirai 2.0 Verification Report

Status: `PARTIALLY_VERIFIED / LOCAL_CONTRACT_TESTS_PASS / REAL_RUNTIME_PENDING`.

## Executed locally

- focused pytest: `28 passed`;
- Python `compileall`: `PASS`;
- direct provider `identity` smoke: `PASS`;
- JSON, TOML, and CSV parsing: `PASS`;
- Python source lines over 100 characters: `0`;
- Moirai-owned changed-path audit: `PASS`;
- SHA-256 manifest verification: `PASS`;
- simple secret-pattern scan: `PASS`.

The focused suite covers strict unknown-key rejection, dynamic position counts, horizons 1/2/5,
legacy schema conversion, context non-clamping, covariate chronology and availability evidence,
required game geometries, license fail-closed behavior, constrained integer projection, exact native
quantile inventory, finite values, crossing rejection, deterministic draw mapping, calendar gaps,
token budgets, package hashes, model hashes, and snapshot mismatch rejection.

## Not executed or certified

- Ruff and mypy were unavailable in the execution environment;
- isolated `uv.lock` resolution and frozen synchronization;
- installation of either runtime lane;
- real Uni2TS import through an isolated lane;
- snapshot download/cache verification against the actual 45.6 MB weight file;
- real model load or q0.1-q0.9 inference;
- separate-process snapshot reload and re-prediction;
- CUDA PID, GPU UUID, VRAM before/peak/after, and external PID matching;
- full repository pytest or GitHub Actions success;
- OOF, Holdout, Prospective, accuracy, baseline superiority, calibration, or fine-tuning;
- shared worker, catalog, CLI, registry, or production integration.

No unexecuted item is represented as success. Research-only license policy keeps production
champion eligibility and automatic promotion disabled.

## Update

Real Uni2TS import, snapshot load, all-nine-quantile inference, separate-process reload, and CUDA
PID/GPU UUID/VRAM evidence have since been executed and certified on the `cuda13-experimental`
lane under a later change. See `docs/moirai2/P8_VERIFICATION_REPORT.md` and
`docs/moirai2/MOIRAI2_RUNTIME_CERTIFICATION.csv` for the current runtime-certification status.
Accuracy, OOF, Holdout, Prospective, and production-champion eligibility remain unexecuted and are
out of scope for that change.
