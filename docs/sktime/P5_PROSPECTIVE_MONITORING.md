# sktime P5 Prospective shadow prediction and monitoring

## Status

```text
IMPLEMENTATION=COMMITTED_TO_DRAFT_PR
P4_PREREQUISITE=VERIFIED_PASS_REQUIRED
SELECTION_SOURCE=P3_OOF_VIA_VERIFIED_P4_LINEAGE
PROSPECTIVE_MODE=SHADOW_ONLY
PRIMARY_METRIC=Hit@±1
MAX_WORKERS=8
NUMERICAL_THREADS_PER_WORKER=1
AUTOMATIC_RETRAINING=false
AUTOMATIC_PROMOTION=false
REAL_TARGET_RUNTIME=EXECUTION_PENDING
```

P5 separates future prediction from later scoring into two independently sealed
stages. P5A creates predictions before future actual values are available. P5B
runs only after those actual values have been independently published.

P5 never uses the Holdout leaderboard to replace the candidate selected by P3
OOF. The P3 OOF-selected candidate, carried through verified P4 evidence, remains
the shadow candidate throughout P5.

## P5A: pre-actual Prospective prediction lock

P5A accepts only observed history and future draw identities. It does not accept
future actual values.

All seven baselines and all four sktime candidates are executed. Random uniform
uses seeds `1`, `2`, and `3`, resulting in 13 candidate/seed rows:

- nine baseline/seed rows;
- four sktime model rows.

Execution uses a bounded thread pool with `max_workers=8`. Results are restored
to the frozen candidate/seed order before hashing, so worker completion order
cannot change the evidence. Numerical-library thread limits are all fixed to one:

```text
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
```

Every row records:

- candidate kind and ID;
- seed;
- fit scope `OBSERVED_HISTORY_ONLY`;
- forecast scope `PROSPECTIVE_DRAW_IDS_ONLY`;
- device, PID, and CPU fallback state;
- raw predictions;
- rounded and legally clipped predictions;
- prediction shape and finite-value state;
- prediction SHA-256;
- `actuals_known=false`;
- `evaluation_status=NOT_SCORED`.

The top-level prediction lock binds:

- Run ID and UTC sealing time;
- Git commit, code hash, and configuration hash;
- verified P4 artifact hash;
- P3 OOF-selected shadow candidate ID;
- observed-history cutoff and SHA-256;
- future draw identities and SHA-256;
- worker and numerical-thread limits;
- every candidate/seed prediction;
- canonical lock seal SHA-256;
- `promotion_status=SHADOW_NOT_PROMOTED`.

## P5A durable evidence

```text
REQUEST_METADATA.json
HISTORY_CONTRACT.json
P4_LINEAGE.json
PROSPECTIVE_PREDICTION_LOCK.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

Raw history values are redacted from request metadata. Their identity remains
verifiable through the external configuration and `HISTORY_CONTRACT.json`.

Formal P5A PASS requires:

- verified P4 `SHA256SUMS`;
- P4 response status `PASS`;
- exact P4 state
  `HOLDOUT_SCORED_NOT_PROMOTED_PROSPECTIVE_REQUIRED`;
- exact P4 OOF-selected candidate lineage;
- all 13 candidate/seed rows present exactly once;
- all 13 rows PASS;
- CPU with no fallback;
- finite predictions with exact shape;
- eight workers and one numerical thread per library;
- no actuals or metrics in the lock;
- matching prediction hashes, canonical seal, manifest, and `SHA256SUMS`.

## P5B: post-reveal monitoring

P5B accepts the immutable P5A lock and independently sourced actual values. It
does not load, fit, retrain, or execute a forecasting model and does not create a
replacement prediction.

P5B recomputes for every sealed candidate/seed row:

- Hit@±1;
- position Hit@±1;
- all-position Hit@±1;
- MAE;
- MSE;
- RMSE.

Seed aggregation retains mean, variance, and worst values. No best seed is
selected. A Prospective leaderboard is retained for audit only and cannot replace
the shadow candidate.

## Drift policy

Default thresholds are:

```text
Hit@±1 target:             0.90
warning Hit@±1 drop:       0.05 versus Holdout
critical Hit@±1 drop:      0.10 versus Holdout
warning MAE increase:      0.50 versus Holdout
critical MAE increase:     1.00 versus Holdout
```

The resulting operational state is one of:

```text
STABLE   -> CONTINUE_SHADOW
WARNING  -> CONTINUE_SHADOW_REVIEW_REQUIRED
CRITICAL -> BLOCK_PROMOTION_RETRAIN_REVIEW_REQUIRED
```

A `CRITICAL` drift state does not mean that artifact verification failed. It
means that the sealed predictions were scored correctly and the observed
performance requires review. Integrity status and operational recommendation are
separate fields.

P5 never performs automatic retraining or automatic promotion. A retraining
recommendation must start a new run with new data, new hashes, new OOF evidence,
and a new pre-actual prediction seal.

## P5B durable evidence

```text
ACTUALS_SNAPSHOT.json
P5_LOCK_LINEAGE.json
PROSPECTIVE_RESULTS.json
CANDIDATE_AGGREGATES.json
PROSPECTIVE_LEADERBOARD.json
DRIFT_REPORT.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

The verifier recomputes all row metrics, seed aggregates, leaderboard ordering,
drift alerts, recommendation, response fields, manifest coverage, and hashes.

## Execute P5A on target Kubuntu

P4 must already have a verified PASS artifact.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin agent/sktime-forecasting-contract-v1
git switch agent/sktime-forecasting-contract-v1
git pull --ff-only

bash scripts/start_sktime_p5_lock_tmux.sh
```

Monitor:

```bash
tmux attach -t sktime-p5-lock
```

The generated lock must be retained unchanged until the corresponding actual
values are published.

## Execute P5B after actual publication

Replace the synthetic contract actuals configuration with a separately reviewed,
immutable real-actuals file and record its source hash before execution.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

export SKTIME_P5_LOCK_EVIDENCE_DIR="/absolute/path/to/prospective-shadow-lock"
export SKTIME_P4_EVIDENCE_DIR="/absolute/path/to/sealed-holdout-score"
export SKTIME_P5_ACTUALS_CONFIG="/absolute/path/to/immutable-prospective-actuals.json"

bash scripts/start_sktime_p5_monitor_tmux.sh
```

Monitor:

```bash
tmux attach -t sktime-p5-monitor
```

## Certification boundaries

The committed synthetic configurations prove contract wiring only. They do not
prove real Prospective accuracy, baseline superiority, or production readiness.
P5 does not claim:

- real P0-P5 target-host execution;
- real prospective Hit@±1, MAE, MSE, or RMSE;
- champion promotion;
- automatic deployment;
- automatic retraining;
- common worker or catalog integration;
- MLflow or PostgreSQL persistence;
- GitHub Actions success;
- merge readiness.
