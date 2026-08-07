# P16 Holdout and Prospective evidence contract

## Purpose

P16 connects the AutoGluon runtime and covariate contracts to chronological Holdout and
Prospective evidence. It does not treat a successful model call as an accuracy result. Prediction
creation and Actual scoring are separate operations with separate immutable artifact roots.

## Safety boundary

The prediction-lock phase receives observed history, future draw identities, a preselected shadow
candidate, three or more model seeds, and prediction values. It must not receive future Actual
values. The lock records:

```text
actual_known=false
evaluation_status=NOT_SCORED
promotion_status=SHADOW_NOT_PROMOTED
automatic_promotion=false
automatic_retraining=false
```

The scoring phase reads only the stored prediction values and independently supplied Actual rows.
It does not import AutoGluon, fit a model, load a predictor, create a replacement forecast, select a
new seed, or replace the shadow candidate.

## Chronological gates

### Holdout lock

The Holdout lock requires:

- immutable history with strictly increasing integer draw IDs;
- future draw IDs after the history cutoff;
- an explicit candidate selected outside Holdout;
- at least three unique model seeds;
- one prediction for every seed and future draw;
- finite predictions with geometry-compatible shape and legal range;
- no field name containing actual, observed, realized, or outcome;
- an absent or empty output directory.

### Holdout score

Holdout scoring requires an independently verified Actual snapshot whose draw IDs exactly match the
lock. It computes the leaderboard for audit, but always returns:

```text
HOLDOUT_SCORED_NOT_PROMOTED_PROSPECTIVE_REQUIRED
```

The Holdout leaderboard cannot replace the shadow candidate.

### Prospective lock

A Prospective lock requires a verified PASS Holdout scoring directory. The candidate ID must match
the Holdout shadow candidate. Holdout reference metrics are copied into Prospective selection
evidence and bound by SHA-256.

### Prospective score

Prospective scoring uses only the sealed prediction values and independently provided Actual rows.
It compares the unchanged shadow candidate against the Holdout reference and returns one operational
state:

```text
STABLE   -> CONTINUE_SHADOW
WARNING  -> CONTINUE_SHADOW_REVIEW_REQUIRED
CRITICAL -> BLOCK_PROMOTION_RETRAIN_REVIEW_REQUIRED
```

Evidence integrity PASS and operational drift are separate. A CRITICAL result does not invalidate a
correctly sealed lock, and it does not trigger automatic retraining.

## Metrics

The primary metric is Hit@±1. The contract also persists:

- position-level Hit@±1;
- all-position Hit@±1;
- exact-hit rate;
- MAE;
- MSE;
- RMSE.

Per-prediction metrics are aggregated to candidate/seed rows before candidate summaries. Candidate
summaries retain mean, variance, and worst values. Best-seed-only selection is prohibited.

## Required baselines

All baselines are generated before Actual values are available and use only the observed history and
legal game geometry:

- seeded random;
- history-independent fixed domain quantiles;
- per-position mean;
- per-position median;
- last value;
- deterministic per-position frequency;
- per-position AR(1) with last-value fallback.

Random uses seeds `[1, 2, 3]`. The fixed baseline does not depend on history or Actual values.

## Durable lock evidence

```text
GEOMETRY.json
HISTORY.json
SELECTION_EVIDENCE.json
MODEL_PREDICTIONS.json
BASELINE_PREDICTIONS.json
PREDICTION_LOCK.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

The verifier rejects missing or extra files, symlinks, special files, incomplete manifests,
SHA-256 mismatches, and lock self-hash mismatch. Lock creation fixes `actual_known=false`.

## Durable scoring evidence

```text
ACTUALS_SNAPSHOT.json
SOURCE_LINEAGE.json
PER_PREDICTION_METRICS.json
PER_SEED_METRICS.json
CANDIDATE_AGGREGATES.json
LEADERBOARD.json
BASELINE_COMPARISON.json
DRIFT_REPORT.json              # Prospective only
SCORING_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

The scorer fingerprints the source tree before work and again before publication. Any mutation of
the source lock aborts scoring.

## Parallelism boundary

The evidence contract records eight outer workers and one nested AutoGluon worker. The current P16
module is a pure evidence and metric layer and does not start parallel model work. Runtime campaigns
must normalize completion order before lock creation.

## Certification boundary

The authoring tests use synthetic histories and supplied prediction values. They verify contracts,
metrics, state transitions, and tamper detection. They do not certify:

- real AutoGluon 1.5.0 execution;
- a real OOF-selected candidate;
- real Holdout or Prospective predictions;
- real Actual publication timing;
- accuracy improvement or baseline superiority;
- external trusted timestamping or digital signatures;
- automatic promotion, registry writes, or production deployment;
- Ruff, mypy, full repository pytest, or GitHub Actions success.
