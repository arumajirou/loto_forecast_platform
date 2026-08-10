# Current Handoff

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T18:20+09:00
repository: arumajirou/loto_forecast_platform
audit_main_sha: cc7ec5473730cfb18100bdfbb5228cf65e571b32
source_of_truth: GitHub + repository code/config
```

## Start here

This handoff is for the next engineer or agent working from the current repository. Re-fetch live GitHub state before mutating branches or merging PRs because the dependency queue may have advanced after this snapshot.

Canonical current-state references:

1. `docs/STATUS.md`
2. `docs/DOCUMENTATION_POLICY.md`
3. `docs/README.md`
4. `docs/MODEL_EXECUTION_MATRIX.md`
5. `docs/UNIFIED_EVALUATION_CAMPAIGN.md`
6. `docs/CURRENT_VERIFICATION_REPORT.md`
7. `docs/CURRENT_RUNBOOK.md`

## Main branch at handoff

```text
main=cc7ec5473730cfb18100bdfbb5228cf65e571b32
```

Merged in the maintenance sequence:

- #248 -> `aae45ba9294499f51cc5f1564de1c6ccf5814230`
- #244 -> `c12ca27048d25cdc869fa3cbbfa6e31c727eb529`
- #242 -> `cc7ec5473730cfb18100bdfbb5228cf65e571b32`

#248 established the unified all-model × all-game development campaign. #244 moved repository workflows to the validated actions/checkout v7 pin. #242 updated the Ray Tune requirement and lock.

## Open PR queue at handoff

### #243 — FastAPI 0.141.1

- Dependabot PR.
- Recreated against audited main.
- Current recreated head at audit: `0f8a0ec9d560d19cb4ee370c3fd2cf667801022f`.
- Mergeability recovered, but exact-head Linux/Windows verification had not completed when the documentation snapshot was cut.
- Do not merge solely because GitHub reports `mergeable=true`.

### #241 — grouped routine dependency update

Includes uvicorn, MLflow, Hypothesis, Ruff and GluonTS changes. It was still rebasing/recreating after the Ray merge. Re-fetch its current head/base before any decision. Because it touches `pyproject.toml` and `uv.lock`, it must be evaluated after any FastAPI merge rather than assumed independent.

## Open scientific/runtime work

### GitHub #239 — Timer Base 84M OOF

This remains the formal leakage-safe real-data OOF workstream. Do not infer OOF success from runtime certification or from the unified campaign implementation.

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

Run from six canonical CSV files:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Expected filenames:

```text
mini.csv
loto6.csv
loto7.csv
bingo5.csv
numbers3.csv
numbers4.csv
```

The campaign is fail-visible. A result matrix may be complete while containing unsupported, unavailable, failed or non-standalone rows.

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

The broad catalog has 174 registered entries at this audit boundary. Do not use that number as any of the following without separate evidence:

- 174 independent forecast candidates;
- 174 shared-routable models;
- 174 runtime-certified models;
- 174 OOF-evaluated models;
- 174 promotable models.

Use `docs/MODEL_EXECUTION_MATRIX.md`, `docs/LIBRARY_RUNTIME_CAPABILITIES.md` and `docs/TSFM_RUNTIME_CAPABILITIES.md` to distinguish those states.

## Before the next GitHub mutation

1. Re-fetch `main` SHA.
2. Re-fetch every open PR's base/head SHA, `mergeable`, draft state and changed-file set.
3. Compare each PR head against live main and reject stale/behind assumptions.
4. Fetch exact-head workflow runs and unresolved review threads.
5. For dependency PRs touching the same lock, merge serially and rebase/recreate the remaining PR after each merge.
6. Use `expected_head_sha` on merge.
7. Re-fetch main after the merge and record the merge SHA.

## What to do next

Repository maintenance next step: finish #243/#241 only after their new exact-head verification is complete.

Research next step: execute the real leakage-safe OOF work in #239 before opening Holdout.

Campaign next step: prepare reviewed immutable six-game historical snapshots, then run the unified development campaign. A real full-catalog execution is an experiment, not a documentation claim.
