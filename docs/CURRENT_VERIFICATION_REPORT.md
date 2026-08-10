# Current Verification Report

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T18:46+09:00
repository: arumajirou/loto_forecast_platform
audit_main_sha: cfbe9f1cf379a68b4ad6ca2bc6d7793dbd828300
scope: repository merge batch + current executable/scientific boundary
```

## Verdict

```text
PR_248_UNIFIED_CAMPAIGN=MERGED_AND_VERIFIED
PR_244_CHECKOUT_V7=MERGED_AND_VERIFIED
PR_242_RAY_TUNE_UPDATE=MERGED_AND_VERIFIED
PR_243_FASTAPI_UPDATE=MERGED_AND_VERIFIED
PR_249_WITHIN_TAU_DECODER=MERGED
PR_241_GROUPED_UPDATE=MERGED_AFTER_CURRENT_HEAD_LINUX_FULL_CI
PR_250_CAMPAIGN_DECODER_ROUTING=CURRENT_BASE_SYNC_AND_CI_PENDING
HOLDOUT=NOT_OPENED
PROSPECTIVE=NOT_OPENED
CHAMPION=NOT_CLAIMED
PROMOTION=NOT_AUTHORIZED
```

## Merged changes and evidence

| PR | Merge SHA | Verification summary |
|---|---|---|
| #248 | `aae45ba9294499f51cc5f1564de1c6ccf5814230` | premerge head `c7c8a039...`; Linux run `31371724178` SUCCESS; Windows run `31371724143` SUCCESS |
| #244 | `c12ca27048d25cdc869fa3cbbfa6e31c727eb529` | actions/checkout v7 workflow update; exact-head Linux and Windows SUCCESS |
| #242 | `cc7ec5473730cfb18100bdfbb5228cf65e571b32` | premerge head `8641a50b...`; Linux `31373320815` SUCCESS; Windows `31373320763` SUCCESS |
| #243 | `b04f3e40baa1861a5b83da047bdef2655905bd52` | premerge head `0f8a0ec9...`; Linux `31373843737` SUCCESS; Windows `31373843656` SUCCESS |
| #249 | `83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f` | premerge head `6571ec99...`; Linux `31374883284` SUCCESS; Windows run `31374883286` was queued when last audited |
| #241 | `cfbe9f1cf379a68b4ad6ca2bc6d7793dbd828300` | current-main premerge head `e5da9364...`; Linux `31376124799` SUCCESS; Windows `31376124812` queued at merge evaluation; GitHub accepted protected expected-head merge |

Queued Windows states are recorded literally and are **not** represented as PASS.

## PR #248 — unified campaign

The merged feature provides:

```bash
uv run loto3 campaign
```

Verified controls include:

- six canonical game geometries;
- complete requested broad-catalog × game materialization;
- fail-visible unsupported/unavailable/non-routable/failed rows;
- Hit@±1 primary tolerance;
- per-position Hit@±1, all-position Hit@±1, MAE, MSE and RMSE;
- seven mandatory baselines;
- all configured seeds with aggregate mean/population variance/worst statistics;
- prediction artifact persistence and SHA-256 sealing before actual scoring read;
- single-use output directories;
- Holdout/Prospective remain unevaluated.

The merge does not establish a real-data 174 × 6 success result.

## PR #249 — within-tau decoder objective

PR #249 changed only:

```text
src/loto/probabilistic/decoder.py
tests/test_hit_at_1_decoder.py
```

It added explicit `MAP` and `WITHIN_TAU` objectives for legal select-game constrained decoding. Focused tests cover exact IID-null optima, brute-force agreement, legality, MAP compatibility and fail-closed probability validation.

This verifies an implementation/theory contract, not a real OOF improvement and not evidence that lottery draws are non-IID.

## PR #241 — dependency group

The merged current-main head `e5da936410a719bf378302cedb34b8addbbbb2a1` was ahead 1 / behind 0 before merge and changed only `pyproject.toml` and `uv.lock`.

The complete Linux CI passed with the new dependency set after #249 was already in its base. The Windows portability lane was queued, not failed, when the expected-head merge was attempted. GitHub accepted the merge under repository protection rules.

The merged dependency boundary includes the intended grouped updates:

- Uvicorn 0.52.1 lane;
- MLflow 3.15.1 lane;
- Hypothesis 6.165.2 lane;
- Ruff 0.16.1 lane;
- GluonTS 0.17.0 lane.

## PR #250 — not merged at audit cutoff

PR #250 proposes routing probability-bearing unified campaign candidate distributions through the explicit Hit@±1 decoder while retaining point-only worker behavior.

At audit cutoff its scientific head had been created before #241 merged. A one-shot branch sync was queued to incorporate current main without modifying its four scientific/test files. Exact current-base CI had therefore not completed. It was correctly left unmerged.

## What this report does not verify

This report does not certify:

- a real six-game immutable data snapshot;
- every third-party model's successful runtime on all games;
- all-model GPU execution;
- a full real-data 174 × 6 campaign;
- an OOF gain from the within-tau decoder;
- Holdout results;
- Prospective results;
- a champion;
- promotion eligibility.

Runtime evidence, decoder/theory evidence, scientific evaluation evidence and documentation evidence remain separate classes.

## Historical report handling

The root `VERIFICATION_REPORT.md` remains a historical version-single-source verification snapshot. Its original evidence is preserved behind a supersession banner. Current readers should use this file plus `docs/STATUS.md`.
