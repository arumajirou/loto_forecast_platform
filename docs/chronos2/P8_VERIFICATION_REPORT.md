# Chronos-2 P8 verification report

## Verdict

`PARTIALLY_VERIFIED`

The calibration implementation and synthetic leakage tests are verified. Real Chronos-2 OOF
predictions have not been calibrated in this authoring environment.

## Executed

- Python 3.13 compileall: PASS
- P8 focused pytest: 47 PASS
- complete P5-P8 focused pytest: 79 PASS
- 100-character Python line gate: PASS
- Python AST parse: PASS
- JSON config parse and Pydantic validation: PASS
- synthetic systematic-bias improvement: PASS
- chronological `fit < conformal < target` proof: PASS
- target and future fold exclusion: PASS
- all-seed retention: PASS
- identical eligible folds across variants: PASS
- missing quantile, duplicate cell, incomplete grid, and actual mismatch rejection: PASS
- Holdout marker rejection: PASS
- atomic artifact publication and SHA-256 verification: PASS
- source input immutability: PASS

## Calibration evidence retained

Each target fold, seed, position, and horizon step records:

- fit fold IDs
- conformal fold IDs
- fit and conformal row counts
- bias offset
- per-level quantile corrections
- per-coverage conformal q-hat values
- fit input SHA-256
- conformal input SHA-256
- target exclusion status
- future fold count used

## Not verified

- real `amazon/chronos-2` OOF input
- measured P8 improvement on a lottery game
- real 80% and 90% prospective coverage
- PyArrow Parquet generation in this authoring environment
- Ruff and mypy in this authoring environment
- full repository pytest
- successful GitHub Actions execution
- Holdout, Prospective, LoRA, full fine-tuning, promotion, or registry integration

## Safety boundary

```text
HOLDOUT_OPENED=false
PROSPECTIVE_OPENED=false
AUTOMATIC_PROMOTION=false
BEST_SEED_ONLY_SELECTION=false
FUTURE_FOLD_COUNT_USED=0
```
