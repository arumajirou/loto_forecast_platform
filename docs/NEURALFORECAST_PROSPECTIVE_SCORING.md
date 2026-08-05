# NeuralForecast Prospective Actual Scoring

## Purpose

This workflow evaluates a previously locked Prospective prediction only after its
actual values are available. Actual values and scores are written to a separate
artifact; the source Prospective run, `PREDICTION_LOCK.json`, and
`VERIFICATION_SEAL.json` remain unchanged.

The primary metric is `Hit@±1`. The same artifact includes:

- position-level `Hit@±1`;
- all-position `Hit@±1`;
- exact hit rate;
- MAE, MSE, and RMSE;
- per-seed values;
- mean, standard deviation, variance, minimum, maximum, and worst-seed values;
- model-versus-baseline deltas.

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

An operator-asserted publication time can be recorded with:

```bash
--actual-published-at 2026-08-05T15:00:00+09:00
```

Verify an artifact read-only:

```bash
uv run loto-auto-campaign \
  verify-scoring \
  --run artifacts/prospective-scoring/<scoring-run>
```

These commands do not load the current campaign YAML. Contracts and prediction
evidence come from the locked source run.

## Source-run requirements

The source must have:

- stage `prospective` and manifest status `PASS`;
- `prediction_lock_status=LOCKED`;
- a valid `PREDICTION_LOCK.json`;
- a valid `VERIFICATION_SEAL.json`;
- a complete valid root `SHA256SUMS`;
- no symbolic links;
- unchanged locked prediction files.

The scorer records source fingerprints before work, checks every copied prediction
against the lock, and re-verifies the source immediately before publishing the
scoring directory.

## Prediction-time history

`--history` must be the exact immutable Raw file used when prediction was created.
Its byte SHA-256 must equal `manifest.json:data_sha256`. A newer dataset containing
actual values is rejected even if earlier rows appear identical.

History is checked against the stored data contract for:

- row count and last draw index;
- draw ID and draw index columns;
- P1 through P5;
- finite integer values;
- Mini Loto range 1 through 31;
- strictly increasing positions;
- duplicate draw IDs and draw indices.

Baseline fitting receives history only. The baseline API has no actual-value
argument.

## Actuals input

`--actuals` must be a distinct CSV or Parquet file containing only the locked
prediction horizon. The scorer requires:

- finite integer draw and number values;
- P1 through P5 in range 1 through 31;
- strictly increasing positions;
- no duplicate draw ID or draw index;
- no draw-ID overlap with history;
- draw indices exactly equal the locked horizon;
- the horizon immediately follows the final history draw.

Both raw actual input and normalized actual values are copied and bound by
`ACTUALS_LOCK.json`.

## Publication-time boundary

When `--actual-published-at` is supplied, it must be at or after the prediction lock
time. The artifact records:

```text
actual_publication_time_provided=true
actual_publication_time_verified=false
```

This is an operator assertion. The implementation does not authenticate an
official publication system, trusted timestamp authority, digital signature, or
transparency log.

## Locked prediction extraction

For every task in `PREDICTION_LOCK.json`, the scorer:

1. resolves the run-relative prediction path;
2. rejects path escape and symbolic links;
3. recomputes and compares SHA-256;
4. copies the exact prediction Parquet bytes;
5. verifies the copy hash;
6. selects the NeuralForecast point column;
7. checks finite values and unique `(ds, unique_id)` keys;
8. verifies a common horizon across tasks.

`TOTAL` from HINT is excluded. P1 through P5 are evaluated. Five position-specific
`u_local` tasks are combined into `u_local_combined` only when all positions exist.

## Fair prediction variants

Every complete draw candidate uses the same variants:

- `raw`;
- `rounded`;
- `reconciled` to a strictly increasing unique integer draw.

Single-position candidates use `raw` and `rounded`; no all-position result is
claimed for an incomplete draw. Ranking uses `reconciled` for complete draws and
`rounded` for single-position rows.

## Required baselines

| Baseline | Prediction-time definition |
|---|---|
| `random_uniform` | Seeded sample without replacement from 1..31, sorted |
| `fixed_center` | History-independent fixed sequence `[6, 11, 16, 21, 26]`, derived only from the 1..31 domain and five positions |
| `mean` | Per-position historical arithmetic mean |
| `median` | Per-position historical median |
| `last` | Most recent historical draw |
| `frequency` | Five most frequent historical numbers with deterministic tie-breaking |
| `statistical_ar1` | Per-position AR(1) with intercept fitted on history by least squares |

AR(1) falls back to the last value only when underidentified or non-finite. Fallback
positions are recorded. Random uses an explicit seed, default `1`. The fixed-value
baseline does not depend on history or actual values.

## Seed aggregation and ranking

`PER_SEED_METRICS` is calculated first. `SEED_SUMMARY` is then calculated from the
per-seed rows and includes mean, standard deviation, variance, minimum, maximum,
seed count, and `worst_seed_hit_pm1`. The best single seed is never selected as the
formal aggregate.

Ranking order is:

1. higher mean `Hit@±1`;
2. higher mean all-position `Hit@±1`;
3. lower mean MAE;
4. lower mean RMSE;
5. higher worst-seed `Hit@±1`.

First place does not automatically promote a model. Deltas against every baseline
are written separately.

## Output

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
PER_SEED_METRICS.{csv,parquet}
SEED_SUMMARY.{csv,parquet}
RANKING.{csv,parquet}
BASELINE_COMPARISON.{csv,parquet}
```

`source_evidence/` contains exact copies of:

- `manifest.json`;
- `campaign_config.json`;
- `data_contract.json`;
- `PROMOTION_GATE.json`;
- `LINEAGE.json`;
- `PREDICTION_LOCK.json`;
- `VERIFICATION_SEAL.json`;
- `VERIFICATION_REPORT.json`;
- `SHA256SUMS`.

Each locked prediction Parquet is also copied and mapped to its task.

## Identity and verification

`scoring_id` is deterministic for the prediction-lock hash, history hash, actuals
hash, scoring-code hash, random seed, actual source label, and asserted publication
time. The code hash covers scoring, baselines, prediction extraction, source
verification, and artifact verification.

`verify-scoring` checks:

- symbolic links and path safety;
- complete `SHA256SUMS`;
- canonical manifest and actual-lock hashes;
- scoring ID and code-hash consistency;
- exact file inventory;
- copied source evidence hashes and sizes;
- copied predictions against the source lock;
- raw history and actual input hashes;
- normalized actual hash and draw indices;
- required metric, per-seed, summary, ranking, and baseline tables;
- the exact seven-baseline set;
- the original source again when it remains available.

If the source is later archived or removed, copied evidence remains verifiable and
the result records `source_reverification=NOT_AVAILABLE`.

## Atomicity

The scorer builds and verifies a temporary directory, then atomically renames it.
Existing outputs are not overwritten. Output inside the source run is rejected.

## Validation boundary

A dependency-minimal baseline/metric smoke executed 9 tests successfully. A second
smoke exercised ingestion, scoring, 24 metric rows, 8 per-seed rows, source
immutability, artifact verification, source deletion, and relocated verification.
That smoke used pandas pickle as a local stand-in for Parquet because `pyarrow` was
not available.

These results do not replace repository Ruff, compileall, mypy, pytest, the formal
Parquet engine, GitHub Actions, or a real locked GPU Prospective run.
