# Loto7 90% ±1 prediction-set design

This module targets **best-of-K simultaneous ±1 coverage**, not a claim that one ticket wins with 90% probability.

## CLI

```powershell
uv run loto experiment coverage --config configs/coverage_90_loto7.yaml
```

The build command uses training, calibration, and validation windows, while leaving the final protected test untouched. It writes:

- `prediction_set.csv` / `prediction_set.json`
- `selection_trace.json`
- `coverage_summary.json`

Explicit one-time certification:

```powershell
uv run loto experiment coverage --config configs/coverage_90_loto7.yaml --certify
```

Certification opens the protected test. Never tune on that result.

## Algorithms

1. Expanding-window point forecasts from robust median, historic average, and recent median.
2. Simultaneous conformal radius from maximum seven-position absolute error.
3. Position probability matrix with robust historical scale.
4. Legal ascending Loto7 candidate generation by beam search.
5. Residual-offset augmentation.
6. Greedy maximum-coverage selection with a diversity term.
7. Calibration, validation, and protected-test Coverage@K reports.

A `TARGET_NOT_MET` result is valid and must not be relabeled as success. Increase candidate-pool diversity, add genuine probabilistic models, or collect more calibration data before certification.
