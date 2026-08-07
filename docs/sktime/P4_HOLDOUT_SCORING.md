# sktime P4 sealed Holdout scoring

## Status

```text
IMPLEMENTATION=COMMITTED_TO_DRAFT_PR
P3_PREREQUISITE=FORMAL_PASS_REQUIRED
SCORING_SCOPE=SEALED_PREDICTIONS_ONLY
MODEL_EXECUTION=FALSE
RETRAINING=FALSE
REPREDICTION=FALSE
PRIMARY_METRIC=Hit@±1
PROMOTION=BLOCKED_UNTIL_PROSPECTIVE
REAL_TARGET_EXECUTION=EXECUTION_PENDING
```

P4 scores Holdout actual values only against predictions that were already
sealed by P3. P4 does not load a sktime estimator, fit a model, select a new
candidate, change a seed, or create a replacement prediction.

The P3 prediction lock is the sole prediction source.

## Required P3 state

The P4 target-host runner refuses to start unless the selected P3 evidence
bundle satisfies all of the following:

1. `sha256sum -c SHA256SUMS` passes;
2. `response.status` is `PASS`;
3. `holdout_status` is `PREDICTIONS_LOCKED_NOT_SCORED`;
4. `promotion_status` is `NOT_PROMOTED`;
5. `HOLDOUT_PREDICTION_LOCK.json` is present and non-empty.

P4 then validates the prediction-lock canonical seal, every per-row prediction
SHA-256, the exact formal candidate and seed inventory, and the Holdout draw
identities.

## Time boundary

The actual-value publication time must be strictly later than the P3 sealing
time:

```text
P3 sealed_at_utc < P4 revealed_at_utc <= P4 scored_at_utc
```

An equal or earlier reveal time is rejected. This prevents evidence from being
represented as pre-actual when the recorded chronology does not prove it.

The repository default actual-value file is synthetic contract data. Its
timestamp is injected at execution time only to verify pipeline wiring. It is
not evidence of a real prospective or pre-publication forecast.

For real data, supply the independently verified official reveal timestamp and
immutable actual-value source file.

## Candidate and seed inventory

Formal P4 requires the same P3 lock inventory:

- random uniform seeds `1`, `2`, and `3`;
- fixed midpoint seed `1`;
- Train mean seed `1`;
- Train median seed `1`;
- Train last seed `1`;
- Train frequency seed `1`;
- seasonal naive seed `1`;
- NaiveForecaster seed `1`;
- PolynomialTrendForecaster seed `1`;
- ExponentialSmoothing seed `1`;
- ThetaForecaster seed `1`.

One missing row, duplicate row, changed seed, or changed ordering prevents formal
certification. Random results are aggregated across all retained seeds. P4 never
selects the best random seed after actual values are known.

## Metrics

Each locked prediction row is scored with:

- Hit@±1;
- position-wise Hit@±1;
- all-position Hit@±1;
- MAE;
- MSE;
- RMSE.

Candidate aggregates retain the mean, population variance, and worst value
across seeds. Position-wise Hit@±1 also retains mean, variance, and worst value.

The Holdout leaderboard uses the same deterministic ordering as Validation and
OOF:

1. mean Hit@±1 descending;
2. mean all-position Hit@±1 descending;
3. mean MAE ascending;
4. candidate ID ascending.

## Baseline comparison

P4 records the OOF-selected candidate's Holdout rank and compares its aggregate
metrics with every formal baseline. Positive `mae_improvement`,
`mse_improvement`, and `rmse_improvement` values mean the selected candidate has
lower error than the baseline. Positive Hit@±1 deltas mean the selected
candidate has a higher Hit@±1 value.

Holdout success does not promote a champion. The required state remains:

```text
HOLDOUT_SCORED_NOT_PROMOTED_PROSPECTIVE_REQUIRED
```

## Durable evidence

```text
REQUEST_METADATA.json
P3_LINEAGE.json
HOLDOUT_ACTUALS.json
HOLDOUT_RESULTS.json
HOLDOUT_CANDIDATE_AGGREGATES.json
HOLDOUT_LEADERBOARD.json
BASELINE_COMPARISON.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

The verifier independently reruns metric calculation from the persisted P3
lock and supplied actual values. It then recomputes candidate aggregates,
leaderboard ordering, baseline deltas, response fields, manifest coverage, and
all SHA-256 values.

P3 lineage includes:

- P3 run ID;
- P3 sealing time;
- prediction-lock seal SHA-256;
- prediction-lock file SHA-256;
- P3 `SHA256SUMS` file SHA-256.

## Target-host execution

P4 requires a verified P3 PASS bundle. By default, the runner selects the newest
`artifacts/sktime-p3/*/oof-holdout-lock` directory.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin agent/sktime-forecasting-contract-v1
git switch agent/sktime-forecasting-contract-v1
git pull --ff-only

bash scripts/start_sktime_p4_certification_tmux.sh
```

Monitor:

```bash
tmux attach -t sktime-p4-certification
```

Select a specific P3 bundle:

```bash
export SKTIME_P3_EVIDENCE_DIR="$PWD/artifacts/sktime-p3/<RUN_ID>/oof-holdout-lock"
bash scripts/start_sktime_p4_certification_tmux.sh
```

For real actual values, also provide the reviewed actual-value file and exact
official publication time:

```bash
export SKTIME_P4_ACTUALS_CONFIG=/absolute/path/to/reviewed_holdout_actuals.json
export SKTIME_P4_REVEALED_AT_UTC=2026-08-05T08:00:00Z
export SKTIME_P4_SCORED_AT_UTC=2026-08-05T08:05:00Z
bash scripts/start_sktime_p4_certification_tmux.sh
```

## Formal success conditions

Formal P4 is PASS only when:

- P3 evidence passes the prerequisite checks;
- the prediction lock seal and file lineage match;
- actual reveal time is after prediction sealing;
- Holdout draw identities match exactly;
- all 13 locked candidate/seed rows are present exactly once;
- every locked row has status PASS;
- prediction shape is identical to Holdout actual shape;
- every prediction is finite;
- every metric recomputes exactly;
- all seed aggregates recompute exactly;
- the leaderboard and baseline comparison recompute exactly;
- model execution, retraining, and reprediction remain false;
- the manifest and SHA256SUMS verify;
- promotion remains blocked.

## Authoring checks

The isolated P4 contract harness reported:

```text
P4_CONTRACT_AND_TAMPER_TESTS=18_PASS
PYTHON_PY_COMPILE=PASS
BASH_SYNTAX=PASS
LINES_OVER_100=0
```

These checks used local contract stubs for existing P3 and metric dependencies.
They verify P4's scoring and evidence logic, but do not certify repository-wide
integration, the target Kubuntu runtime, real actual-value provenance, or real
Holdout accuracy.

## Boundaries

P4 does not claim:

- real target-host execution;
- real-data Hit@±1, MAE, MSE, or RMSE;
- superiority over a baseline;
- a promoted champion;
- Prospective performance;
- a production deployment decision;
- GitHub Actions success;
- merge readiness.
