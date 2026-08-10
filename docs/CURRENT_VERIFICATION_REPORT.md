# Current Verification Report

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T18:59+09:00
repository: arumajirou/loto_forecast_platform
audit_main_sha: 8430d9f507ba735bf1df69930e057c974752bfdb
scope: repository merge batch + executable/scientific boundary
```

## Verdict

```text
PR_248_UNIFIED_CAMPAIGN=MERGED_AND_VERIFIED
PR_244_CHECKOUT_V7=MERGED_AND_VERIFIED
PR_242_RAY_TUNE_UPDATE=MERGED_AND_VERIFIED
PR_243_FASTAPI_UPDATE=MERGED_AND_VERIFIED
PR_249_WITHIN_TAU_DECODER=MERGED
PR_241_GROUPED_UPDATE=MERGED_AFTER_CURRENT_HEAD_LINUX_FULL_CI
PR_250_CAMPAIGN_DECODER_ROUTING=MERGED_AFTER_CURRENT_BASE_LINUX_FULL_CI
HOLDOUT=NOT_OPENED
PROSPECTIVE=NOT_OPENED
CHAMPION=NOT_CLAIMED
PROMOTION=NOT_AUTHORIZED
```

## Merge/CI evidence

| PR | Merge SHA | Verification summary |
|---|---|---|
| #248 | `aae45ba9294499f51cc5f1564de1c6ccf5814230` | premerge head `c7c8a039...`; Linux `31371724178` SUCCESS; Windows `31371724143` SUCCESS |
| #244 | `c12ca27048d25cdc869fa3cbbfa6e31c727eb529` | actions/checkout v7 update; exact-head Linux and Windows SUCCESS |
| #242 | `cc7ec5473730cfb18100bdfbb5228cf65e571b32` | premerge head `8641a50b...`; Linux `31373320815` SUCCESS; Windows `31373320763` SUCCESS |
| #243 | `b04f3e40baa1861a5b83da047bdef2655905bd52` | premerge head `0f8a0ec9...`; Linux `31373843737` SUCCESS; Windows `31373843656` SUCCESS |
| #249 | `83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f` | premerge head `6571ec99...`; Linux `31374883284` SUCCESS; Windows `31374883286` was queued when last audited |
| #241 | `cfbe9f1cf379a68b4ad6ca2bc6d7793dbd828300` | current-main premerge head `e5da9364...`; Linux `31376124799` SUCCESS; Windows `31376124812` queued at merge evaluation; GitHub accepted protected expected-head merge |
| #250 | `8430d9f507ba735bf1df69930e057c974752bfdb` | current-main synchronized head `c3cefc9c...`; Linux `31376812517` SUCCESS through full pytest/clean-tree; review threads 0; Windows `31376812289` queued and not treated as PASS |

Queued Windows states are recorded literally and are not represented as successful evidence.

## Unified campaign state

The merged campaign provides `uv run loto3 campaign` and enforces the development-only comparison contract:

- canonical six-game geometry;
- complete requested broad-catalog × game materialization;
- fail-visible unsupported/unavailable/non-routable/failed rows;
- Hit@±1 primary tolerance;
- per-position Hit@±1, all-position Hit@±1, MAE, MSE and RMSE;
- seven mandatory baselines;
- all configured seeds with aggregate variance/worst statistics;
- prediction persistence and SHA-256 sealing before actual scoring read;
- single-use output directories;
- Holdout and Prospective remain unevaluated.

PR #250 now routes probability-bearing candidate estimators through family-specific WITHIN_TAU decoding while leaving point-only workers point-only and preserving explicit distribution/decoder identity in runtime evidence.

## Decoder evidence boundary

PR #249 added explicit `MAP` / `WITHIN_TAU` constrained select-game objectives. PR #250 added digit-family WITHIN_TAU probability decoding and connected the unified candidate route to the appropriate family-specific decoder.

This verifies code/theory/routing contracts. It does **not** verify a real-data OOF gain, non-IID draws, a Holdout winner, or promotion eligibility.

## Dependency boundary

Audited main includes FastAPI `>=0.141.1,<0.142`, Ray Tune `>=2.56.1`, and the grouped #241 Uvicorn/MLflow/Hypothesis/Ruff/GluonTS updates with a committed consistent `uv.lock`.

## What this report does not verify

This report does not certify:

- a real six-game immutable data snapshot;
- every third-party model's successful runtime on all games;
- all-model GPU execution;
- a full real-data 174 × 6 campaign;
- an OOF gain from the WITHIN_TAU decoder;
- Holdout results;
- Prospective results;
- a champion;
- promotion eligibility.

Runtime evidence, decoder/theory evidence, scientific evaluation evidence and documentation evidence remain separate classes.

## Historical report handling

The root `VERIFICATION_REPORT.md` remains a historical version-single-source verification snapshot. Its original evidence is preserved behind a supersession banner. Current readers should use this file plus `docs/STATUS.md`.
