# P8D Verification Report

Status: `PARTIALLY_VERIFIED / ORCHESTRATOR_LOCAL_PASS / TARGET_HOST_EXECUTION_PENDING`.

## Executed locally

- strict seven-stage state machine: `PASS`;
- state payload SHA-256 and event hash chain: `PASS`;
- invalid transition and repeated-stage rejection: `PASS`;
- artifact directory tree SHA-256: `PASS`;
- symlink rejection: `PASS`;
- candidate result, static review, violation, and lock-SHA validation: `PASS`;
- manifest tamper rejection: `PASS`;
- installation applied-status and human-review validation: `PASS`;
- timezone-aware review-time enforcement: `PASS`;
- candidate-to-install lock-SHA binding: `PASS`;
- concurrent record lock: `PASS`;
- control checkpoint and manifest refresh: `PASS`;
- generated operator-command ordering and approval placeholders: `PASS`.

## Not executed or certified

- actual `uv lock` resolution;
- actual dependency or license approval;
- target-host lock installation;
- supported CPU campaign;
- CUDA campaign and GPU evidence;
- real P8C pair verification;
- Ruff, mypy, full repository pytest, or successful GitHub Actions steps;
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, calibration, or baselines.

Local success verifies orchestration behavior only. It does not verify Uni2TS or the target-host
runtime. P9 remains closed until the real seven-stage sequence completes.
