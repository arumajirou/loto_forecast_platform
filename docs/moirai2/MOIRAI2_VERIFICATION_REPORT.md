# Moirai 2.0 Verification Report

Status: `PARTIALLY_VERIFIED / P8B_LOCK_REVIEW_LOCAL_PASS / TARGET_HOST_PENDING`.

## Retained evidence

- P0-P6 Contract v2 and focused tests from PR #83;
- P7 covariate compilation, native field wiring, hashes, and fake-boundary tests from PR #86;
- P8 two-process reload, prediction hash, forward-device, and GPU evidence logic from PR #87;
- P8A deterministic six-case campaign and all-case formal gate from PR #89.

## P8B executed locally

- exact direct-dependency pin parsing: `PASS`;
- non-destructive candidate generation boundary: `PASS` with mocked `uv lock`;
- registry package inventory and dependency-edge accounting: `PASS`;
- registry artifact hash requirement: `PASS`;
- VCS, path, and editable source rejection: `PASS`;
- unsupported source and unresolved dependency rejection: `PASS`;
- direct dependency version mismatch rejection: `PASS`;
- multi-version package warning retention: `PASS`;
- failed automated review approval rejection: `PASS`;
- reviewer and timezone-aware review evidence: `PASS`;
- dry-run installation leaves the lane and candidate artifact unchanged: `PASS`;
- explicit token and expected candidate-lock SHA guard: `PASS`;
- atomic installation of lock, report, and approval with separate evidence: `PASS`;
- existing-lock replacement SHA guard: `PASS`;
- installed lock/report/approval cross-hash validation: `PASS`;
- tampered lock, report, missing approval, and lane mismatch rejection: `PASS`;
- P8A preflight integration: `PASS`;
- focused pytest: `36 passed`.

## Static gates

- Python compileall: `PASS`;
- structured JSON and CSV parsing: `PASS`;
- Python source lines over 100 characters: `0`;
- P8B delta SHA-256 manifest: `PASS`;
- cumulative manifest cross-check: `PASS`;
- simple secret-pattern scan: `PASS`.

## Not executed or certified

- real `uv lock` resolution for either isolated lane;
- human dependency graph review or installation into a target-host lane;
- frozen synchronization and frozen import/device probe;
- real Uni2TS import, snapshot load, predictor, or all-nine-quantile inference;
- twelve real provider processes across the six formal cases;
- real GPU PID, UUID, VRAM, or post-exit release evidence;
- Ruff, mypy, full repository pytest, or successful GitHub Actions steps;
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, calibration, or baselines.

Automated review success is not represented as human approval. Candidate generation does not modify
a runtime lane. Research-only licensing continues to block production champion eligibility,
automatic promotion, and commercial deployment.
