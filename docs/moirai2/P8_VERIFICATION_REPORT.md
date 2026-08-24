# P8 Verification Report

Status: `PARTIALLY_VERIFIED / RUNTIME_CERTIFIED_CUDA13 / ACCURACY_PENDING`.

RUNTIME_CERTIFIED = YES (cuda13-experimental lane only). ACCURACY_CERTIFIED = NO.
PRODUCTION_CHAMPION_ELIGIBLE = NO (CC-BY-NC-4.0, research-only license lane).

## Executed on target host (RTX 5070 Ti, cuda13-experimental)

- reviewed `uv.lock` resolution and frozen synchronization: `PASS`;
- real `uni2ts==2.0.0` import through the reviewed isolated lane: `PASS`;
- real pinned snapshot load (`Salesforce/moirai-2.0-R-small@30f43ff0`) and all-nine-quantile
  inference: `PASS`;
- two real provider processes using the target snapshot, exact prediction-hash match across
  distinct PIDs: `PASS`;
- actual external GPU PID, GPU UUID, VRAM before/peak/after, and post-exit release evidence:
  `PASS`;
- all 6 formal P8A cases (draw/calendar × target-only/past-only/past-known-future): `6/6 PASS`.

Evidence: `RUN_ID=moirai2-p8-campaign-20260824T144850Z`,
`/mnt/e/env/ts/loto_gpu_runs/moirai2-p8-campaign-20260824T144850Z/`, 148/148 files SHA-256
verified against `SHA256SUMS`, `campaign_summary.json` (`formal_runtime_certified: true`,
`passed_case_count: 6`, `required_case_count: 6`, `holdout_opened: false`, `oof_opened: false`,
`prospective_opened: false`, `accuracy_claimed: false`).

## Executed locally

- runtime certification pure tests: `PASS`;
- torch forward-hook input/output device observation: `PASS` on CPU;
- fake Torch/GluonTS/Uni2TS provider boundary: `PASS`;
- strict external GPU CSV parsing: `PASS`;
- distinct-process and exact prediction-hash comparison: `PASS`;
- changed-quantile rejection: `PASS`;
- artifact and covariate identity comparison: `PASS`;
- CPU fallback and missing CUDA PID rejection: `PASS`;
- provider PID release validation: `PASS`;
- certification CLI and provider runner compileall: `PASS`;
- Python source lines over 100 characters: `0`.

## Not executed or certified

- the `supported-py311` lane (no CUDA13 lane executed there);
- full repository pytest or successful GitHub Actions CI steps (only focused-scope Ruff, mypy,
  and pytest have been run so far);
- OOF, Holdout, Prospective, accuracy, calibration, baseline superiority, or fine-tuning.

No fake, mocked, or source-inspection evidence is represented as real model-runtime certification.
Real target-host CUDA13 runtime certification is evidenced above and does not extend to accuracy
or production-champion eligibility.
