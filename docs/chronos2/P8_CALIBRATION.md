# Chronos-2 P8 chronological calibration

## Status

`IMPLEMENTED / LOCALLY_VERIFIED / REAL_OOF_PENDING / HOLDOUT_CLOSED`

P8 consumes only the P7 OOF prediction and fold tables. It does not read Holdout or
Prospective data and does not promote a model automatically.

## Chronological split inside each target fold

For every target OOF fold, all earlier folds are divided chronologically into two disjoint
sets:

```text
bias and quantile fit folds < conformal score folds < target fold
```

The target fold and every future fold are excluded from all calibration fitting. Early folds
without enough history receive `NOT_APPLICABLE_WARMUP` and are excluded from every variant so
comparisons use identical target folds.

Default minimums:

- bias and quantile fit: 3 prior folds
- conformal scoring: 2 later prior folds
- conformal fraction: 0.4

## Calibration variants

P8 evaluates four variants on the same eligible folds and seeds:

1. `chronos2_uncalibrated`
2. `chronos2_bias_calibrated`
3. `chronos2_bias_quantile_calibrated`
4. `chronos2_bias_quantile_conformal`

Bias is fitted per seed, position, and horizon step from `actual - raw_point`. The calibrated
point is passed through the same `round_clip_unique_sort_v1` reconciliation used by P7.

Quantile correction is fitted per seed, position, horizon step, and quantile level from the
empirical residual quantile. Monotone rearrangement removes crossing after correction.

Conformal intervals use chronological split conformalized quantile regression. Quantile
corrections are fitted on the earlier fit folds. Nonconformity scores are calculated only on
the later conformal folds, and the finite-sample `higher` quantile expands the 80% and 90%
interval endpoints.

## Required input

- `CHRONOS2_OOF_PREDICTIONS.csv`
- `CHRONOS2_OOF_FOLDS.csv`
- a P8 calibration JSON config

The source prediction table may contain baseline rows, but calibration reads only the exact
`source_candidate`. The source candidate must contain a complete fold, seed, position, and
horizon grid with explicit seeds and the configured quantile columns.

Any Holdout or Prospective marker, missing quantile, duplicate source cell, non-finite value,
inconsistent actual across seeds, incomplete grid, or non-chronological fold metadata fails
closed.

## Metrics

Hit@±1 remains the primary metric. P8 also saves:

- all-position Hit@±1
- position-level Hit@±1
- MAE, MSE, and RMSE
- Pinball Loss and CRPS approximation
- 80% and 90% coverage and interval width
- calibration error and quantile crossing count
- fold and seed aggregates, including worst seed and worst fold

No variant is automatically promoted. Holdout remains closed until the complete model,
configuration, seed aggregation, and calibration policy are fixed.

## Command

```bash
python scripts/run_chronos2_calibration.py \
  --predictions /absolute/path/CHRONOS2_OOF_PREDICTIONS.csv \
  --folds /absolute/path/CHRONOS2_OOF_FOLDS.csv \
  --config configs/chronos2_campaign/p8_calibration.example.json \
  --output /absolute/path/chronos2-p8-output
```

The output directory must be absent or empty. Results are generated in a staging directory and
published atomically only after all tables, the report, manifest, and SHA-256 inventory are
written.
