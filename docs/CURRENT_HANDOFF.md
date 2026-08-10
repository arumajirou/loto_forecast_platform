# Current Handoff

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T18:46+09:00
repository: arumajirou/loto_forecast_platform
audit_main_sha: cfbe9f1cf379a68b4ad6ca2bc6d7793dbd828300
source_of_truth: live GitHub + repository code/config + exact-head CI evidence
```

## Start here

This handoff records the repository after the safe merge batch completed in this maintenance session. Re-fetch live GitHub state before the next mutation because a new scientific PR (#250) was already created concurrently after the dependency merges.

Canonical current-state references:

1. `docs/STATUS.md`
2. `docs/CURRENT_VERIFICATION_REPORT.md`
3. `docs/CURRENT_RUNBOOK.md`
4. `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md`
5. `docs/UNIFIED_EVALUATION_CAMPAIGN.md`
6. `docs/MODEL_EXECUTION_MATRIX.md`
7. `docs/DOCUMENTATION_POLICY.md`
8. `docs/README.md`

## Main branch at handoff

```text
main=cfbe9f1cf379a68b4ad6ca2bc6d7793dbd828300
```

Merged in or during the maintenance sequence:

- #248 -> `aae45ba9294499f51cc5f1564de1c6ccf5814230`
- #244 -> `c12ca27048d25cdc869fa3cbbfa6e31c727eb529`
- #242 -> `cc7ec5473730cfb18100bdfbb5228cf65e571b32`
- #243 -> `b04f3e40baa1861a5b83da047bdef2655905bd52`
- #249 -> `83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f` (merged concurrently by another repository workstream)
- #241 -> `cfbe9f1cf379a68b4ad6ca2bc6d7793dbd828300`

#248 established the unified all-model × all-game development campaign. #249 added the explicit Hit@±tau constrained decoder objective while preserving MAP compatibility. #244/#242/#243/#241 updated workflow/dependency boundaries.

## Open PR queue at handoff

### #250 — route unified candidate distributions through Hit@±1 decoder

At the audit cutoff:

- PR is Draft.
- Original head `4f6f3a9bab78e20f344d2cfc190ac971b4adf90e` was one commit behind after #241 merged.
- Its original exact-head Linux full CI passed before the #241 dependency merge.
- A branch-only one-shot sync was created to merge current `main` into the PR branch without editing its scientific files; that sync and the resulting current-base CI were still queued on the self-hosted Linux runner at cutoff.
- Unresolved review threads were 0 when checked.
- No Holdout, Prospective, raw-data, model-artifact, dependency/lock, promotion or champion changes are in #250's declared scope.

Decision: `CURRENT_BASE_SYNC_AND_CI_PENDING`. Do not merge #250 from its stale pre-#241 head merely because its old Linux CI passed.

## Open scientific/runtime work

### GitHub #239 — Timer Base 84M OOF

This remains the formal leakage-safe real-data OOF workstream. Do not infer OOF success from runtime certification, the unified campaign implementation, or decoder-theory work.

Required scientific ordering remains:

```text
Train/development -> OOF evidence -> Holdout gate -> Prospective gate -> promotion decision
```

Holdout and Prospective remain closed.

### GitHub #118 — Timer-S1 PR-B

This remains an immutable runtime/certification workstream. Required work includes provenance hashing, remote-code review, isolated runtime, real inference, device evidence, reload/reproducibility and fail-closed certification. It does not authorize OOF or accuracy claims.

## Unified campaign now available

Plan the complete matrix without running models:

```bash
uv run loto3 campaign --output unused --plan-only
```

Run from canonical game CSV files:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

The campaign is fail-visible. A result matrix may be complete while containing unsupported, unavailable, failed or non-standalone rows.

## Decoder state

Merged PR #249 provides:

```text
DecodeObjective.MAP
DecodeObjective.WITHIN_TAU
```

for legal select-game constrained decoding. It is a decoder objective implementation, not OOF evidence and not proof that lottery draws are non-IID. PR #250 proposes routing probability-bearing unified-campaign candidate estimators through this objective; that integration was still pending current-base verification at handoff.

## Current dependency boundary

Audited main includes:

- FastAPI `>=0.141.1,<0.142`;
- Ray Tune `>=2.56.1` in the `full` extra;
- Uvicorn `>=0.52.1` where declared;
- MLflow `>=3.15.1` where declared;
- Hypothesis `>=6.165.2` in dev dependencies;
- Ruff `>=0.16.1` in dev dependencies;
- GluonTS `>=0.17.0` in the frameworks extra;
- the corresponding committed `uv.lock` from #241.

The final #241 current-main head passed the complete Linux CI before merge. Its native Windows run was still queued when GitHub accepted the protected expected-head merge; this queued state must not be rewritten as PASS.

## Scientific invariants to preserve

- Primary metric: Hit@±1.
- Also report position Hit@±1, all-position Hit@±1, MAE, MSE and RMSE.
- Mandatory baselines: random, fixed, mean, median, last, frequency, statistical AR(1).
- Chronological splits only.
- Fit scaler/encoder/feature selection/HPO only inside eligible training data.
- Retain every configured seed and aggregate mean, population variance and worst performance.
- Do not select a model from its best seed only.
- Seal predictions with SHA-256 before corresponding actuals are read.
- Never overwrite raw source data.
- Runtime availability is not runtime certification; runtime certification is not forecast accuracy.

## Runtime interpretation

The broad catalog has 174 registered entries at this audit boundary. Do not use that count as a synonym for 174 independent forecasters, 174 shared-routable models, 174 runtime-certified models, 174 OOF-evaluated models, or 174 promotable models.

## Before the next GitHub mutation

1. Re-fetch `main` SHA and all Open PRs.
2. Re-fetch each PR's base/head SHA, draft/mergeable state and changed-file set.
3. Compare head against live main; do not silently accept behind branches for scientific changes.
4. Fetch exact-head workflow runs and unresolved review threads.
5. For dependency PRs sharing `pyproject.toml`/`uv.lock`, merge serially and regenerate the remaining PR after each merge.
6. Use `expected_head_sha` on merge.
7. Preserve queued/cancelled/failed states literally; only completed success is PASS.

## What to do next

Repository maintenance next step: finish #250 only after its current-main synchronization and exact-head CI complete.

Research next step: execute the real leakage-safe OOF work in #239 before opening Holdout.

Campaign next step: prepare reviewed immutable six-game historical snapshots, then execute the unified development campaign. A real full-catalog execution is an experiment, not a documentation claim.
