# sktime P2 chronological Validation benchmark

## Status

```text
IMPLEMENTATION=COMMITTED_TO_DRAFT_PR
EVALUATION_STAGE=VALIDATION_ONLY
FIT_SCOPE=TRAIN_ONLY
HOLDOUT_SCOPE=HASH_ONLY_NOT_SCORED
PRIMARY_METRIC=Hit@±1
REAL_TARGET_RUNTIME=EXECUTION_PENDING
PROMOTION=NOT_ALLOWED
```

P2 adds a leakage-resistant chronological benchmark contract after P0 discovery
and P1 fit/predict/save/load certification. It evaluates fixed sktime models and
baseline methods under the same Train-only fit and Validation-only scoring
boundary.

P2 does not score Holdout, does not create Prospective predictions, and does not
promote a champion.

## Chronological split

The input matrix must be pre-sorted, unique, finite, gap-free, and positionally
valid. The split is explicit:

```text
Train -> Validation -> Holdout
```

For the P2 Validation stage:

- candidates receive only Train values;
- metrics use only Validation values;
- Holdout values are represented only by a SHA-256 identity in the evidence;
- Holdout values are not copied into generated artifacts;
- changing Holdout cannot change Train or Validation hashes.

## Candidates

Formal baselines:

- random uniform;
- fixed midpoint;
- Train mean;
- Train median;
- Train last value;
- Train frequency/mode;
- seasonal naive.

Formal sktime models:

- NaiveForecaster;
- PolynomialTrendForecaster;
- ExponentialSmoothing;
- ThetaForecaster.

All model constructors remain frozen by the P1 matrix contract.

## Metrics

The primary metric is `hit_at_1`, the fraction of all position predictions whose
absolute error is at most one. P2 also records:

- position-wise Hit@±1;
- all-position Hit@±1 per draw;
- MAE;
- MSE;
- RMSE.

Predictions are rounded to the nearest integer and clipped to legal position
bounds before scoring. Raw and postprocessed predictions are both retained.

## Multiple seeds

The random baseline runs with seeds `1`, `2`, and `3`. P2 stores mean, variance,
and worst value for every aggregate metric. It never promotes a best seed.

Deterministic baselines and deterministic sktime candidates use seed `1`.

## Leaderboard

Validation ranking uses, in order:

1. mean Hit@±1 descending;
2. mean all-position Hit@±1 descending;
3. mean MAE ascending;
4. candidate ID ascending.

The first row is recorded as `best_validation_candidate` for inspection only.
The required promotion state remains:

```text
VALIDATION_ONLY_NOT_PROMOTED
```

## Artifacts

```text
REQUEST_METADATA.json
DATA_CONTRACT.json
VALIDATION_ACTUALS.json
CANDIDATE_RESULTS.json
SEED_AGGREGATES.json
LEADERBOARD.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

`REQUEST_METADATA.json` redacts raw values. The external request remains the
verification source. Manifests and SHA-256 cover all emitted evidence.

## Execute on target Kubuntu

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin agent/sktime-forecasting-contract-v1
git switch agent/sktime-forecasting-contract-v1
git pull --ff-only

bash scripts/start_sktime_p2_certification_tmux.sh
```

Monitor:

```bash
tmux attach -t sktime-p2-certification
```

## Formal success conditions

P2 is formally verified only when:

- the isolated Python 3.12 lock resolves and is reviewed;
- exact sktime 1.0.1 is installed;
- all seven baselines pass;
- all four sktime candidates pass for every position;
- all metrics recompute exactly from persisted predictions and Validation actuals;
- random seeds are exactly `[1, 2, 3]`;
- seed aggregates and leaderboard recompute exactly;
- fit scope is Train-only;
- evaluation scope is Validation-only;
- Holdout remains hash-only and unscored;
- manifests and SHA256SUMS verify;
- aggregate benchmark status is PASS.

## Boundaries

P2 does not claim:

- Holdout performance;
- Prospective performance;
- OOF or rolling-origin cross-validation;
- HPO or feature selection;
- model ensemble performance;
- superiority over baselines;
- Hit@±1 improvement;
- champion promotion;
- common worker/catalog integration;
- GitHub Actions success;
- merge readiness.
