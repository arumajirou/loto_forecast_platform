# P8C Verification Report

Status: `PARTIALLY_VERIFIED / EVIDENCE_GATE_LOCAL_PASS / REAL_CAMPAIGNS_PENDING`.

## Executed locally

- complete synthetic CPU/CUDA evidence-pair verification: `PASS`;
- strict campaign manifest and SHA-256 revalidation: `PASS`;
- all-six-case and 24-process evidence accounting: `PASS`;
- all-nine-quantile shape, finite, monotonic, and q0.5 checks: `PASS`;
- separate-process response and prediction identity checks: `PASS`;
- run-evidence file-hash and embedded-response checks: `PASS`;
- GPU monitor PID, UUID, memory, and release rederivation: `PASS`;
- CPU no-GPU-process observation: `PASS`;
- source commit/tree and principal-file identity checks: `PASS`;
- clean-tree wrapper sealing and launch-evidence checks: `PASS`;
- tamper, missing-evidence, CPU fallback, and cross-lane mismatch rejection: `PASS`;
- focused pytest: `37 passed`;
- Python compileall: `PASS`;
- Python source lines over 100 characters: `0`.

## Not executed or certified

- real reviewed lock resolution or approval;
- real supported CPU campaign;
- real CUDA13 campaign;
- real 24-process evidence set;
- real Uni2TS import, snapshot load, quantile inference, or GPU observation;
- Ruff, mypy, full repository pytest, or successful GitHub Actions steps;
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, calibration, or baselines.

Synthetic campaign fixtures and mocked subprocess boundaries are not represented as real runtime
certification. P9 remains closed until the independent verifier passes real CPU and CUDA campaigns.
