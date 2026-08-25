# P8A Verification Report

Status: `IMPLEMENTED / LOCAL_PURE_TESTS_PASS / TARGET_HOST_CUDA13_PASS`.

## Target-host results (cuda13-experimental)

All 6 formal cases executed on the RTX 5070 Ti target host with real Uni2TS import, real pinned
snapshot load, real quantile inference, and two-process CUDA observation: `6/6 PASS`. Evidence:
`RUN_ID=moirai2-p8-campaign-20260824T144850Z`
(`/mnt/e/env/ts/loto_gpu_runs/moirai2-p8-campaign-20260824T144850Z/`). See
`docs/moirai2/P8_VERIFICATION_REPORT.md` for the consolidated evidence summary. The
`supported-py311` lane has not been executed.

## Local results

- focused pytest: `19 passed`;
- Python compileall: `PASS`;
- Python lines over 100 characters: `0`;
- six formal cases and ordering: `PASS`;
- deterministic seed and request construction: `PASS`;
- calendar missing-period fixture: `PASS`;
- exact covariate length and availability evidence: `PASS`;
- reviewed-lock and lock-version fail-closed checks: `PASS`;
- snapshot required-file checks: `PASS`;
- formal all-case aggregation: `PASS`;
- partial campaign remains non-formal: `PASS`;
- missing-case and changed-comparison rejection: `PASS`.

## Boundary

The local results above cover the authoring environment only: no network dependency resolution,
real lock review, frozen synchronization, Uni2TS import, model load, prediction, or CUDA
observation was performed there. Those items have since been executed and passed on the target
host (see above). Full repository pytest and successful GitHub Actions CI steps remain
outstanding; only focused-scope Ruff, mypy, and pytest have been run to date.
