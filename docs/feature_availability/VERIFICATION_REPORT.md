# Feature Availability Registry Foundation Verification Report

## Status

`PARTIALLY_VERIFIED / SYNTHETIC_CONTRACT_TESTS_PASS / REAL_FEATURES_NOT_MIGRATED`

## Repository audit

The current main branch already contains:

- normalized-frame provenance completeness checks;
- chronological development/holdout and rolling-fold logic;
- a `protocol_hash` that rejects cross-protocol metric comparison;
- permutation, time-shift, and direct feature-causality sentinels;
- provider-specific covariate contracts in open Draft PRs.

It does not contain one common Registry that combines feature identity, source bytes, source
revision, prediction cutoff, temporal class, materialization bytes, split use, and preprocessor-fit
evidence. No branch or open PR named Feature Availability Registry was found before implementation.

## Implemented scope

```text
src/loto/feature_availability/__init__.py
src/loto/feature_availability/contracts.py
src/loto/feature_availability/manifest.py
src/loto/feature_availability/validator.py
tests/feature_availability/test_registry_foundation.py
docs/feature_availability/DATA_CONTRACT.md
docs/feature_availability/MIGRATION_GUIDE.md
docs/feature_availability/VERIFICATION_REPORT.md
```

No existing feature builder, provider, data source, split implementation, evaluation orchestration,
root dependency, lockfile, workflow, Holdout, Prospective, or production deployment path is changed.

## Executed validation

The exact proposed package and tests were executed locally with synthetic evidence only:

```text
focused pytest=19 passed
Python compileall=PASS
Python source line length <=100=PASS
Ruff=PENDING_TOOL_UNAVAILABLE
mypy=PENDING_TOOL_UNAVAILABLE
full repository pytest=PENDING
GitHub Actions=CI_BLOCKED_PRE_RUN
```

Focused tests cover:

- one valid synthetic manifest;
- strict unknown-field rejection;
- deterministic atomic writer, SHA-256 sidecar, read-back, and overwrite refusal;
- tamper rejection;
- cutoff violation;
- unknown revision;
- future-target dependency;
- scaler/preprocessor fit on Validation, Holdout, and Prospective;
- target actual use from Validation, Holdout, and Prospective;
- duplicate feature identity;
- changed source hash;
- unknown temporal class;
- false prediction-time availability assertion;
- split overlap/order violation;
- typed fail-closed exception.

## Evidence boundary

All feature values, hashes, timestamps, splits, and preprocessors used by the tests are synthetic.
The tests validate the contract, validator, and writer; they do not inspect the repository's real
feature outputs or any production/development dataset.

## Explicit non-claims

```text
existing feature migration=NOT_PERFORMED
real data provenance reverified=NOT_PERFORMED
real external-variable vintage verified=NOT_PERFORMED
real scaler/encoder fit evidence=NOT_COLLECTED
real Validation/Holdout/Prospective access audit=NOT_PERFORMED
real feature manifests emitted before prediction=NOT_PERFORMED
real-data leakage absence=NOT_PROVEN
production deployment=NOT_PERFORMED
```

## GitHub Actions

The PR-head workflow ended before any observable step was created:

```text
workflow=ci
run_number=2777
run_id=31080592616
job=test
job_id=92548277217
conclusion=failure
steps=null
logs_url=null
classification=CI_BLOCKED_PRE_RUN
```

Checkout, Python setup, dependency installation, Ruff, compileall, mypy, and pytest did not
start. This is not evidence of a Feature Availability implementation or test failure. No rerun was
requested.
