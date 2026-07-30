# Loto Forecast Platform v3.1.0 — 90% ±1 Coverage Implementation

## Implemented

- Prediction-set coverage module under `src/loto/coverage/`
- Best-of-K simultaneous ±1 coverage evaluation
- Element-level ±1, row-level ±1, best MAE, exact-row and positions-covered metrics
- Simultaneous conformal calibration radius
- Position probability matrices with robust historical scale
- Legal Loto7 beam-search candidate generation
- Residual-offset candidate augmentation
- Greedy maximum-coverage selection with diversity penalty
- Protected train/calibration/validation/test split
- Explicit one-time certification command that opens the protected test
- CSV/JSON artifacts and selection trace
- CLI: `loto experiment coverage --config ...`
- Example config: `configs/coverage_90_loto7.yaml`
- Design guide: `docs/COVERAGE_90_DESIGN.md`
- MLForecast irregular-date fix: integer draw index and `freq=1`
- `ridge-position`, `elasticnet-position`, and `lightgbm-position` routed through a lag-regression position worker

## Verification

- Full pytest suite: PASS
- Total tests: 319 passed
- Coverage smoke run: PASS, returned `TARGET_NOT_MET` honestly on sample data
- Protected test remains unopened by the normal build command

## Important interpretation

The implementation targets a measured **best-of-K prediction-set coverage rate**. It does not claim that a single ticket has a 90% chance of winning. If validation coverage is below 90%, the result is reported as `TARGET_NOT_MET`; the system does not relabel failure as success.

## Commands

```powershell
uv sync --frozen --extra dev --extra full
uv run loto experiment coverage --config configs/coverage_90_loto7.yaml
```

One-time protected-test certification:

```powershell
uv run loto experiment coverage --config configs/coverage_90_loto7.yaml --certify
```
