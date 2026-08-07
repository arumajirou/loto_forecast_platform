# Moirai 2.0 Verification Report

Status: `PARTIALLY_VERIFIED / P8C_EVIDENCE_GATE_LOCAL_PASS / REAL_CAMPAIGNS_PENDING`.

## Retained evidence

- P0-P6 Contract v2 and focused tests from PR #83;
- P7 covariate compilation, native field wiring, hashes, and fake-boundary tests from PR #86;
- P8 two-process reload, prediction hash, forward-device, and GPU evidence logic from PR #87;
- P8A deterministic six-case campaign and all-case formal gate from PR #89;
- P8B reviewed-lock candidate, approval, installation, and preflight gate from PR #91.

## P8C executed locally

- clean Git commit/tree and principal-source identity capture: `PASS`;
- formal wrapper source injection and output resealing: `PASS`;
- complete synthetic supported CPU and CUDA evidence-pair verification: `PASS`;
- manifest accounting and every SHA-256 recalculation: `PASS`;
- request seed, local-only snapshot, and model revision checks: `PASS`;
- all-six-case validation for each lane: `PASS`;
- two distinct provider processes per case: `PASS`;
- all-nine-quantile finite, shape, monotonic, and q0.5 checks: `PASS`;
- exact reload prediction, model, artifact, and covariate identity checks: `PASS`;
- run-evidence file hashes and embedded response checks: `PASS`;
- CPU no-GPU-process verification: `PASS`;
- CUDA monitor PID, UUID, peak memory, and release rederivation: `PASS`;
- cross-lane source and pinned model artifact equality: `PASS`;
- tamper, missing evidence, CPU fallback, and mismatch rejection: `PASS`;
- focused pytest: `37 passed`.

## Static gates

- Python compileall: `PASS`;
- structured JSON and CSV parsing: `PASS`;
- Python source lines over 100 characters: `0`.

## Not executed or certified

- real lock resolution, human approval, or target-host lock installation;
- real supported CPU or CUDA13 six-case campaigns;
- real 24-provider-process evidence pair;
- real Uni2TS import, snapshot load, predictor, quantiles, or GPU evidence;
- Ruff, mypy, full repository pytest, or successful GitHub Actions steps;
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, calibration, or baselines.

P8C local success verifies the verifier, not the model runtime. `p9_oof_gate_open` remains false until
real immutable CPU and CUDA campaigns pass the independent evidence gate. Research-only licensing
continues to block production champion eligibility, automatic promotion, and commercial deployment.
