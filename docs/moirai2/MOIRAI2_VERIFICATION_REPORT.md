# Moirai 2.0 Verification Report

Status: `PARTIALLY_VERIFIED / P8A_CAMPAIGN_LOCAL_PASS / REAL_RUNTIME_PENDING`.

## Retained evidence

- P0-P6 Contract v2 and focused tests from PR #83;
- P7 covariate compilation, native field wiring, hashes, and fake-boundary tests from PR #86;
- P8 two-process reload, prediction hash, forward-device, and GPU evidence logic from PR #87.

## P8A executed locally

- exact six-case request matrix generation: `PASS`;
- deterministic target history and fixed seed 1: `PASS`;
- draw-sequence gap-free timestamps: `PASS`;
- calendar-time timestamps with intentional missing periods: `PASS`;
- exact past-only and known-future feature lengths: `PASS`;
- known-at-prediction-time evidence with no actual-value marker: `PASS`;
- reviewed-lock presence and exact lock-version rejection logic: `PASS`;
- snapshot required-file and SHA-256 evidence: `PASS`;
- all-six-case formal gate and subset non-formal behavior: `PASS`;
- missing case and changed reload flag rejection: `PASS`;
- focused pytest: `19 passed`;
- Python compileall: `PASS`;
- Python source lines over 100 characters: `0`.

## Not executed or certified

- actual isolated lockfile resolution or human lock review;
- frozen synchronization and frozen import/device probe on the target host;
- real Uni2TS import, snapshot load, predictor, or all-nine-quantile inference;
- twelve real provider processes across the six formal cases;
- real GPU PID, UUID, VRAM, or post-exit release evidence;
- Ruff, mypy, full repository pytest, or successful GitHub Actions steps;
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, calibration, or baselines.

The generated covariates are deterministic runtime-certification features, not proposed forecasting
features. No accuracy or leakage-superiority claim is made. Research-only licensing continues to
block production champion eligibility, automatic promotion, and commercial deployment.
