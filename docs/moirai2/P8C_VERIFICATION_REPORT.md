# P8C Verification Report

Status: `PARTIALLY_VERIFIED / EVIDENCE_GATE_LOCAL_PASS_AND_TARGET_HOST_CUDA13_PASS / SUPPORTED_CPU_CAMPAIGN_PENDING`.

## Executed on target host (cuda13-experimental)

- real reviewed lock resolution and approval: `PASS` (`LOCK_REVIEW_REPORT.json` +
  `LOCK_REVIEW_APPROVAL.json`, lock SHA-256 cross-verified in campaign preflight);
- real CUDA13 campaign, all 6 formal cases: `6/6 PASS`;
- real Uni2TS import, snapshot load, quantile inference, and GPU observation: `PASS`.

Evidence: `RUN_ID=moirai2-p8-campaign-20260824T144850Z`. The real supported CPU campaign has not
been executed; P9 remains closed until that campaign also passes.

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

- real supported CPU campaign;
- full repository pytest or successful GitHub Actions CI steps (only focused-scope Ruff, mypy,
  and pytest have been run to date);
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, calibration, or baselines.

Synthetic campaign fixtures and mocked subprocess boundaries are not represented as real runtime
certification independent of the target-host evidence cited above. P9 remains closed until the
independent verifier also passes a real CPU campaign.
