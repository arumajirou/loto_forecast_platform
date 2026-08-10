# Current Handoff

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T18:59+09:00
repository: arumajirou/loto_forecast_platform
audit_main_sha: 8430d9f507ba735bf1df69930e057c974752bfdb
source_of_truth: live GitHub + repository code/config + exact-head CI evidence
```

## Start here

Canonical current-state references:

1. `docs/STATUS.md`
2. `docs/CURRENT_VERIFICATION_REPORT.md`
3. `docs/CURRENT_RUNBOOK.md`
4. `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md`
5. `docs/UNIFIED_EVALUATION_CAMPAIGN.md`
6. `docs/MODEL_EXECUTION_MATRIX.md`
7. `docs/DOCUMENTATION_POLICY.md`
8. `docs/CURRENT_ARTIFACT_MANIFEST.md`
9. `docs/README.md`

## Main branch at handoff

```text
main=8430d9f507ba735bf1df69930e057c974752bfdb
```

Merged in or during this maintenance sequence:

- #248 -> `aae45ba9294499f51cc5f1564de1c6ccf5814230`
- #244 -> `c12ca27048d25cdc869fa3cbbfa6e31c727eb529`
- #242 -> `cc7ec5473730cfb18100bdfbb5228cf65e571b32`
- #243 -> `b04f3e40baa1861a5b83da047bdef2655905bd52`
- #249 -> `83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f` (merged concurrently by another repository workstream)
- #241 -> `cfbe9f1cf379a68b4ad6ca2bc6d7793dbd828300`
- #250 -> `8430d9f507ba735bf1df69930e057c974752bfdb`

At the 18:59 JST audit cutoff, the only remaining open PR was the documentation refresh PR #251 itself.

## Evaluation/decoder state

`uv run loto3 campaign` is the canonical development-only broad-catalog × six-game comparison surface.

PR #249 provides explicit `MAP` and `WITHIN_TAU` constrained select-game decoding. PR #250 extends the integration so probability-bearing unified-campaign candidate estimators are decoded with family-specific WITHIN_TAU objectives:

- digit games: digit-family window-mass WITHIN_TAU decoding;
- select games: legal constrained WITHIN_TAU DP;
- point-only workers: remain point-only and continue through the point legalisation route;
- candidate probability adapter: explicitly identified as row-normalized slot-binary probability rather than a native categorical PMF;
- decoder/distribution identities: retained in runtime evidence and therefore in the sealed evaluation lineage.

This is implementation/routing evidence. It does not establish a real OOF gain, non-IID draws, a Holdout winner, or promotion.

## Current dependency boundary

Audited main includes:

- FastAPI `>=0.141.1,<0.142` where declared;
- Ray Tune `>=2.56.1` in the `full` extra;
- Uvicorn 0.52.1 lane;
- MLflow 3.15.1 lane;
- Hypothesis 6.165.2 lane;
- Ruff 0.16.1 lane;
- GluonTS 0.17.0 lane;
- the corresponding committed `uv.lock`.

## Open scientific/runtime work

### GitHub #239 — Timer Base 84M OOF

This remains the formal leakage-safe real-data OOF workstream. Do not infer OOF success from runtime certification, unified-campaign implementation, or decoder-theory work.

Required ordering remains:

```text
Train/development -> OOF evidence -> Holdout gate -> Prospective gate -> promotion decision
```

Holdout and Prospective remain closed.

### GitHub #118 — Timer-S1 PR-B

This remains an immutable runtime/certification workstream. Required work includes provenance hashing, remote-code review, isolated runtime, real inference, device evidence, reload/reproducibility and fail-closed certification. It does not authorize OOF or accuracy claims.

## Unified campaign commands

Plan only:

```bash
uv run loto3 campaign --output unused --plan-only
```

Run:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

A complete matrix can contain unsupported, unavailable, failed or non-standalone rows. Do not drop those rows from coverage reporting.

## Scientific invariants

- Primary metric: Hit@±1.
- Also report per-position Hit@±1, all-position Hit@±1, MAE, MSE and RMSE.
- Mandatory baselines: random, fixed, mean, median, last, frequency, statistical AR(1).
- Chronological splits only.
- Fit scaler/encoder/feature selection/HPO only inside eligible training data.
- Retain every configured seed and aggregate mean, population variance and worst performance.
- Do not select a model from its best seed only.
- Seal predictions with SHA-256 before corresponding actuals are read.
- Never overwrite raw source data.
- Runtime availability is not runtime certification; runtime certification is not forecast accuracy.

## Before the next GitHub mutation

1. Re-fetch live `main` and Open PR search.
2. Re-fetch PR base/head SHA, draft/mergeable state, changed files, exact-head CI and unresolved review threads.
3. Reject stale scientific branches unless current-base integration is separately validated.
4. Merge dependency/lock PRs serially.
5. Use `expected_head_sha`.
6. Record queued/cancelled/failed Actions states literally rather than calling them PASS.

## Next research step

Execute the real leakage-safe OOF work in #239 before opening Holdout. For the unified campaign, prepare reviewed immutable six-game historical snapshots and execute the real development campaign; do not treat implementation completion as a forecast-quality result.
