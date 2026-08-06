# Chronos-2 P5-P7 Runtime and OOF

Status: `IMPLEMENTED / DEPENDENCY-MINIMAL_TESTED / REAL_RUNTIME_PENDING`

## P5-P6 runtime matrix

The runtime matrix covers:

- Z0 position-local, horizon 1;
- Z1 position-panel with cross-learning, horizon 1;
- Z2 multivariate, horizon 5;
- Z3 past-only covariates, horizon 2;
- Z4 known-future covariates, horizon 2.

Z3 and Z4 run control and perturbed requests. A formal PASS requires both responses to pass
shape, finite-value, quantile-monotonicity and no-CPU-fallback checks, and requires the covariate
perturbation to change the point forecast. Every control and perturbed request and response is
retained under `scenarios/<scenario-id>/` with complete SHA-256 coverage.

Injected test doubles can produce only `PARTIALLY_VERIFIED`. Only `runtime_mode=real` can produce
formal `PASS`.

## P7 chronological OOF

`run_oof_evaluation` creates expanding-window folds. Each fold passes only the training slice to the
Chronos-2 predictor and every baseline. Validation rows are used only after predictions exist.
Draw numbers are unique, strictly increasing and gap-free by default. Draw dates are unique and
strictly increasing. Validation overlap is rejected unless explicitly enabled.

Primary metric:

- Hit@±1.

Also retained:

- all-position Hit@±1;
- MAE, MSE and RMSE;
- per-position metrics;
- Pinball Loss and quantile-based CRPS approximation;
- 80% and 90% coverage and interval width when corresponding quantiles are available;
- calibration error and quantile-crossing count;
- fold mean and worst-fold Hit@±1;
- seed mean, population variance, minimum, maximum and worst-seed Hit@±1.

Required baselines:

- random;
- fixed;
- mean;
- median;
- last;
- frequency;
- seasonal naive;
- AR(1) statistical baseline.

The same point postprocessing is applied to Chronos-2 and every baseline:

```text
round -> candidate-range clip -> duplicate reconciliation -> sort policy
```

Raw point values remain in `raw_point`; scored values remain in `point` with
`prediction_variant=reconciled`.

No best-seed-only selection is allowed. Holdout and Prospective are not opened by P7. The report
binds source data, configuration, prediction values, metrics and evaluation source code with
SHA-256.
