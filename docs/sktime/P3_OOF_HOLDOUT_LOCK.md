# sktime P3 rolling-origin OOF and Holdout prediction lock

## Status

```text
IMPLEMENTATION=COMMITTED_TO_DRAFT_PR
P3_SCOPE=TRAIN_ONLY_OOF_AND_PRE_ACTUAL_HOLDOUT_LOCK
TARGET_RUNTIME=sktime==1.0.1
REAL_TARGET_EXECUTION=EXECUTION_PENDING
HOLDOUT_SCORE=NOT_PERFORMED
PROMOTION=NOT_ALLOWED
```

P3 follows P2 Validation benchmarking. It adds expanding-window out-of-fold
assessment inside Train and freezes every candidate/seed Holdout prediction
before Holdout actuals may be scored.

## Chronological boundary

Formal flow:

```text
Train
  ├─ expanding-window OOF folds
  └─ OOF candidate ranking

Train + Validation
  └─ fit every candidate and freeze all Holdout predictions

Holdout actuals
  └─ not read, not copied, not scored in P3
```

OOF test blocks never cross the Train endpoint. Validation is not used in OOF.
Validation becomes visible only for final pre-Holdout fitting after the P2
artifact has independently passed verification.

## Formal rolling geometry

The synthetic contract configuration uses:

```text
Train rows        21
Validation rows    4
Holdout rows       5
Initial OOF train  9
Fold horizon       3
Step length        3
OOF folds          4
```

Folds are:

```text
fit [0:9]   score [9:12]
fit [0:12]  score [12:15]
fit [0:15]  score [15:18]
fit [0:18]  score [18:21]
```

## Candidate and seed policy

Every P2 baseline and P1 sktime model runs on every OOF fold. Random uniform
runs seeds 1, 2, and 3. Other deterministic candidates retain seed 1 as their
execution identity.

P3 performs two aggregation levels:

1. fold metrics per candidate and seed;
2. seed-level mean, variance, and worst value per candidate.

Best-seed-only selection is impossible because the leaderboard uses the
candidate aggregate across all retained seeds.

## Primary and secondary metrics

```text
Primary:   Hit@±1
Secondary: position Hit@±1
           all-position Hit@±1
           MAE
           MSE
           RMSE
```

Leaderboard ordering is deterministic:

1. higher mean Hit@±1;
2. higher mean all-position Hit@±1;
3. lower mean MAE;
4. lexical candidate ID.

The top OOF candidate is recorded for inspection. P3 does not promote it.

## Holdout prediction lock

After OOF completes, every candidate and every retained random seed is fitted on
Train plus Validation and predicts the Holdout draw identities. Holdout actual
values are not passed to prediction functions.

The lock records:

- Run ID;
- UTC sealing timestamp;
- Git commit;
- code SHA-256;
- configuration SHA-256;
- P2 validation artifact SHA-256;
- visible Train+Validation values SHA-256;
- Holdout draw identities and SHA-256;
- all candidate/seed raw and postprocessed predictions;
- per-row prediction SHA-256;
- selected OOF candidate ID;
- canonical lock seal SHA-256.

Changing only Holdout actual values must not change the prediction lock. Tests
verify this invariance directly.

## P2 lineage prerequisite

The P3 runner refuses to start without a verified P2 benchmark directory. It:

1. verifies the P2 `SHA256SUMS`;
2. requires P2 `response.status=PASS`;
3. requires `VALIDATION_ONLY_NOT_PROMOTED`;
4. hashes the P2 `SHA256SUMS` file;
5. binds that digest into the P3 prediction lock.

Set an explicit P2 directory with:

```bash
export SKTIME_P2_BENCHMARK_DIR=/path/to/artifacts/sktime-p2/<run>/benchmark
```

Otherwise, the runner selects the newest matching P2 benchmark directory.

## Durable artifacts

P3 emits:

```text
REQUEST_METADATA.json
DATA_CONTRACT.json
OOF_FOLDS.json
OOF_RESULTS.json
OOF_SEED_METRICS.json
OOF_CANDIDATE_AGGREGATES.json
OOF_LEADERBOARD.json
HOLDOUT_PREDICTION_LOCK.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

Raw dataset values are redacted from request metadata. OOF actuals are retained
because they are Train rows. Holdout actuals are never copied into generated P3
artifacts; only their external-input hash appears in the data contract.

## Verification gates

The verifier reconstructs and checks:

- exact fold geometry;
- Train-prefix and OOF future-block hashes;
- draw identities;
- exact candidate/seed inventory on every fold;
- prediction shape and finite values;
- every metric;
- both aggregation levels;
- leaderboard order;
- selected candidate identity;
- exact candidate/seed inventory in the Holdout lock;
- Holdout prediction shape and finite values;
- no actuals or metrics in the Holdout lock;
- UTC timestamp format;
- per-row prediction hashes;
- canonical lock seal;
- manifest coverage;
- portable SHA-256 coverage.

Formal PASS requires every OOF row and every locked Holdout prediction row to
PASS. PARTIAL or FAILED evidence remains verifiable but is never certified.

## Target-host execution

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin agent/sktime-forecasting-contract-v1
git switch agent/sktime-forecasting-contract-v1
git pull --ff-only

bash scripts/start_sktime_p3_certification_tmux.sh
```

Monitor:

```bash
tmux attach -t sktime-p3-certification
```

## Synthetic-data boundary

`rolling_origin_oof.json` is a wiring and leakage contract. Its results are not
real-data accuracy evidence and cannot support a baseline-superiority,
Holdout-performance, or Prospective-performance claim.

## Next stage

P4 may score only a previously sealed `HOLDOUT_PREDICTION_LOCK.json` after
actuals are independently revealed and verified. It must reject unsealed,
changed, late-created, partial, or post-actual predictions.
