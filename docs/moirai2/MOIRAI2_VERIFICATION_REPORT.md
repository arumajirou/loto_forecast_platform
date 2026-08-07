# Moirai 2.0 Verification Report

Status: `PARTIALLY_VERIFIED / P8_HARNESS_LOCAL_PASS / REAL_RUNTIME_PENDING`.

## Retained evidence

- P0-P6 Contract v2 and focused tests from PR #83;
- P7 covariate compilation, native field wiring, hashes, and fake-boundary tests from PR #86.

## P8 executed locally

- canonical request and prediction SHA-256 utilities: `PASS`;
- strict GPU/process CSV parsers: `PASS`;
- torch forward input/output device hook: `PASS` on CPU;
- fake provider runner device evidence: `PASS`;
- distinct-process reload comparison: `PASS` with synthetic responses;
- changed quantile, same PID, CPU fallback, and missing external CUDA PID rejection: `PASS`;
- model artifact and covariate identity comparison: `PASS`;
- provider PID post-exit release gate: `PASS`;
- certification CLI and runner compileall: `PASS`;
- Python source lines over 100 characters: `0`.

## Not executed or certified

- resolved isolated lockfiles or frozen synchronization;
- real Uni2TS import, snapshot load, predictor, or all-nine-quantile inference;
- two real provider processes and exact real prediction equality;
- real GPU PID, UUID, VRAM, or post-exit release evidence;
- Ruff, mypy, full repository pytest, or successful GitHub Actions steps;
- OOF, Holdout, Prospective, accuracy, calibration, baselines, or fine-tuning.

No unexecuted item is represented as success. Research-only licensing continues to block production
champion eligibility, automatic promotion, and commercial deployment certification.
