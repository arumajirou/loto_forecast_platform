# NeuralForecast Prospective Actual Scoring

## Purpose

This workflow evaluates a previously locked Prospective prediction only after the
corresponding actual values are available. It never writes actual values, scores,
or reports into the source Prospective run.

The priority metric is `Hit@±1`. The same artifact also reports:

- position-level `Hit@±1`;
- all-position `Hit@±1`;
- exact hit rate;
- MAE;
- MSE;
- RMSE;
- mean, standard deviation, minimum, maximum, and worst-seed `Hit@±1`;
- comparison with required baselines.

## Commands

Create a scoring artifact:

```bash
uv run loto-auto-campaign \
  score-prospective \
  --run artifacts/miniloto-all-auto/<locked-prospective-run> \
  --history runs/data-acquisition-all/mini/normalized/mini.csv \
  --actuals inputs/verified_actual_values.csv \
  --output artifacts/prospective-scoring/<scoring-run> \
  --random-seed 1 \
  --actual-source-label "operator-verified source"
```

An operator-asserted publication time can be recorded:

```bash
  --actual-published-at 2026-08-05T15:00:00+09:00
```

Verify an existing scoring artifact read-only:

```bash
uv run loto-auto-campaign \
  verify-scoring \
  --run artifacts/prospective-scoring/<scoring-run>
```

Both commands are configless. They do not load the current campaign YAML.
Contracts and prediction evidence come from the locked source run.

## Source-run preconditions

The source run must satisfy all of the following:

- stage is `prospective`;
- run manifest status is `PASS`;
- `prediction_lock_status=LOCKED`;
- `PREDICTION_LOCK.json` verifies;
- `VERIFICATION_SEAL.json` verifies;
- complete root `SHA256SUMS` verifies;
- no symbolic links;
- every locked task prediction remains unchanged.

Scoring records source fingerprints before work starts, checks every copied
prediction against the lock, and re-verifies the source run before publishing the
output directory.

## History contract

`--history` is the immutable Raw file used when the prediction was produced.
Its byte-level SHA-256 must equal `manifest.json:data_sha256` in the source run.
A newer dataset that already contains actual values is rejected, even if its
historical rows appear equivalent.

History must also match the stored data contract:

- row count;
- last draw index;
- number-column names;
- integer and finite values;
- Mini Loto bounds 1 through 31;
- strictly increasing positions;
- no duplicate draw ID or draw index.

Baselines are fitted only from this prediction-time history. Actual values are not
accepted by the baseline-generation API.

## Actuals contract

`--actuals` must be a separate CSV or Parquet file containing only the draw or
draws represented by the locked prediction horizon.

Required checks:

- integer and finite draw index and number values;
- Mini Loto bounds 1 through 31;
- strictly increasing P1 through P5;
- no duplicate draw ID or draw index;
- no draw-ID overlap with prediction-time history;
- draw indices exactly equal the locked prediction horizon;
- the horizon immediately follows the last history draw.

The raw actual input and its normalized form are copied into the scoring artifact
and bound by `ACTUALS_LOCK.json`.

## Timestamp boundary

`PREDICTION_LOCK.json` contains a local UTC lock timestamp. When
`--actual-published-at` is supplied, the scorer requires it to be at or after the
prediction lock timestamp.

The field means that an operator supplied a timestamp. The implementation records:

```text
actual_publication_time_provided=true
actual_publication_time_verified=false
```

It does not independently authenticate an official publication system, trusted
timestamp authority, transparency log, or digital signature. External proof is a
separate future capability.

## Prediction extraction

For every task listed in `PREDICTION_LOCK.json`, the scorer:

1. resolves the run-relative prediction path;
2. rejects path escape and symbolic links;
3. recomputes the prediction SHA-256;
4. compares it with the lock record;
5. copies the exact Parquet bytes into `source_predictions/`;
6. verifies the copy SHA-256;
7. selects the NeuralForecast point column;
8. checks finite values and unique `(ds, unique_id)` keys;
9. verifies all tasks use the same horizon.

`TOTAL` from HINT predictions is excluded from position scoring. P1 through P5 are
scored. Five position-specific `u_local` tasks are also combined into a comparable
`u_local_combined` draw candidate when all positions are present.

## Prediction variants

Every complete draw candidate is evaluated under identical variants:

- `raw`;
- `rounded`;
- `reconciled` to the nearest strictly increasing unique integer sequence.

Single-position `u_local` candidates use `raw` and `rounded`; all-position
`Hit@±1` is not claimed for an incomplete draw.

The primary ranking variant is:

- `reconciled` for complete draws;
- `rounded` for single-position candidates.

## Required baselines

All baselines use prediction-time history only.

| Baseline | Definition |
|---|---|
| `random_uniform` | Seeded sample without replacement from 1..31, sorted per draw |
| `fixed_center` | Per-position midpoint between historical minimum and maximum |
| `mean` | Per-position historical arithmetic mean |
| `median` | Per-position historical median |
| `last` | Most recent historical draw |
| `frequency` | Five most frequent historical numbers, deterministic tie-breaking |
| `statistical_ar1` | Per-position AR(1) with intercept fitted by least squares |

The statistical baseline falls back to the last value only when AR(1) is
underidentified or produces non-finite output. Fallback positions are recorded.
Random uses an explicit seed, defaulting to `1`.

## Ranking order

Candidates are ranked by:

1. higher mean `Hit@±1`;
2. higher mean all-position `Hit@±1`;
3. lower mean MAE;
4. lower mean RMSE;
5. higher worst-seed `Hit@±1`.

A model is not promoted merely because it ranks first. The report separately
records deltas against every baseline.

## Output layout

```text
ACTUALS_LOCK.json
ARTIFACT_MANIFEST.json
SCORING_REPORT.json
SHA256SUMS
SOURCE_PREDICTION_MAP.json
BASELINE_METADATA.json
inputs/
source_evidence/
source_predictions/
HISTORY_NORMALIZED.{csv,parquet}
ACTUALS_NORMALIZED.{csv,parquet}
MODEL_PREDICTIONS.{csv,parquet}
BASELINE_PREDICTIONS.{csv,parquet}
SCORED_PREDICTIONS.{csv,parquet}
METRICS.{csv,parquet}
POSITION_METRICS.{csv,parquet}
SEED_SUMMARY.{csv,parquet}
RANKING.{csv,parquet}
BASELINE_COMPARISON.{csv,parquet}
```

The source evidence directory contains exact copies of the source manifest,
prediction lock, verification seal, verification report, and root SHA manifest.
Each locked prediction Parquet is copied separately and mapped back to its task.

## Scoring identity

`scoring_id` is deterministic for:

- prediction-lock SHA-256;
- history SHA-256;
- actuals SHA-256;
- scoring-code SHA-256;
- random seed;
- actual source label;
- operator-asserted publication time.

The scoring-code hash covers the scorer, baseline generator, prediction extractor,
source verifier, and scoring verifier implementations.

## Artifact verification

`verify-scoring` checks:

- no symbolic links;
- complete `SHA256SUMS`;
- canonical manifest and actuals-lock hashes;
- consistent scoring ID and scoring-code hash;
- exact file inventory;
- copied source evidence hashes and sizes;
- copied prediction hashes against `PREDICTION_LOCK.json`;
- raw history and actual input hashes;
- normalized actual hash and draw indices;
- required metric tables and columns;
- exact required baseline set;
- original source re-verification when the source remains available.

When the original source directory has been archived or removed, verification can
still succeed from copied evidence and prediction files. The result records
`source_reverification=NOT_AVAILABLE` rather than pretending the source was read.

## Atomicity and immutability

The scorer builds and verifies a temporary artifact first, then atomically renames
it to the requested output. Existing output directories are never overwritten.
The output must not be inside the source Prospective run.

The source prediction run is read-only. Actual values, baseline predictions,
metrics, rankings, and reports are written only to the separate scoring directory.

## Validation boundary

Committed tests cover baseline determinism, metrics, combined local candidates,
ranking, end-to-end scoring, source immutability, source removal, mutation
detection, history mismatch, actual horizon mismatch, and configless CLI routing.

Repository Ruff, compileall, mypy, pytest, GitHub Actions, and a real locked GPU
Prospective run must still execute before formal certification.
