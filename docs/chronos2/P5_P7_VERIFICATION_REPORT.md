# Chronos-2 P5-P7 Verification Report

Status: `PARTIALLY_VERIFIED`

## Executed locally

- Python `compileall`: PASS
- focused P5-P7 tests: 32 passed
- focused source coverage: 91%
- Python AST parse: PASS
- JSON parse: PASS
- 100-character source and test line gate: PASS
- secret-pattern scan: PASS
- synthetic OOF artifact generation and SHA verification: PASS
- synthetic runtime-matrix artifact generation and SHA verification: PASS

## Verified contracts

- Z0-Z4 scenario construction;
- local, panel/cross-learning and multivariate request separation;
- past and known-future covariate control/perturbation evidence;
- injected runtime cannot claim formal PASS;
- shape, quantile, finite-value and CPU-fallback matrix gates;
- expanding chronological OOF;
- no Validation rows passed to the predictor;
- gap-free draw-number and monotonic-date checks;
- all configured seeds retained;
- Hit@±1, all-position Hit@±1, MAE, MSE and RMSE;
- Pinball Loss, CRPS approximation, coverage, width and calibration metrics;
- random, fixed, mean, median, last, frequency, seasonal-naive and AR(1) baselines;
- raw and reconciled point-prediction preservation;
- fold, seed and worst-case summaries;
- atomic artifact publication and complete SHA-256 manifests;
- Holdout and Prospective remain unopened.

## Not verified

- `chronos-forecasting==2.3.1` installation in the isolated environment;
- generated and reviewed `uv.lock`;
- real `amazon/chronos-2` snapshot load;
- real CPU or RTX 5070 Ti inference;
- real covariate perturbation effect;
- GPU UUID, PID, VRAM and no-fallback evidence;
- real OOF accuracy or baseline superiority;
- Ruff, mypy, full repository pytest or GitHub Actions.

No accuracy, promotion, Holdout or Prospective claim is made.
