# P8D Verification Report

Status: `PARTIALLY_VERIFIED / ORCHESTRATOR_LOCAL_PASS_AND_TARGET_HOST_CUDA13_PASS / SUPPORTED_LANE_PENDING`.

## Executed on target host (cuda13-experimental)

- actual `uv lock` resolution: `PASS`;
- actual dependency and license approval (`APPLY-REVIEWED-MOIRAI2-LOCK`,
  `LOCK_REVIEW_APPROVAL.json`): `PASS`;
- target-host lock installation: `PASS`;
- CUDA campaign and GPU evidence, all 6 formal cases: `6/6 PASS`.

Evidence: `RUN_ID=moirai2-p8-campaign-20260824T144850Z`; lock SHA-256
`cb88264ab130d41ac588c529e683d806691699caf398ef53609f13866f59da24` cross-verified in campaign
preflight. Real P8C independent-verifier pair verification against this target-host evidence has
not been separately confirmed and remains listed below.

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

- supported CPU campaign;
- real P8C independent-verifier pair verification against the target-host evidence above;
- full repository pytest or successful GitHub Actions CI steps (only focused-scope Ruff, mypy,
  and pytest have been run to date);
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, calibration, or baselines.

Local success verifies orchestration behavior; the target-host CUDA13 evidence above verifies
Uni2TS and the target-host runtime for that lane. P9 remains closed until the supported CPU lane
also completes the real seven-stage sequence.
