# P9 Historical forecasts, backtest, and residual contract

## Scope

P9 certifies the Darts `historical_forecasts()`, `backtest()`, and `residuals()`
interfaces without treating API availability as successful execution.

## Temporal rules

- `start` is interpreted as the first forecast origin.
- `overlap_end` is fixed to `false`.
- Every forecast window must be fully contained in observed history.
- `stride`, horizon, and `last_points_only` determine an exact expected key set.
- Missing, duplicate, or unexpected origin/target/position keys fail closed.
- `retrain=true` requires a fit at every origin.
- `retrain=false` requires explicit prefit evidence and no new fits.
- Integer retrain cadence requires the exact expected fit-origin sequence.

## Metric parity

Manual metrics are calculated from the canonical historical point ledger:

- Hit@±1;
- position-wise Hit@±1;
- all-position Hit@±1;
- MAE;
- MSE;
- RMSE.

Darts `backtest()` must match manual MAE, MSE, and RMSE within declared absolute
and relative tolerances. Hit@±1 remains the platform-primary metric and is not
silently replaced by a Darts default metric.

## Residual parity

The canonical residual sign is `actual - prediction`. Darts `residuals()` must
match the canonical ordered residual vector. Shape, sign, finite values, and
ordering are all certified. The report retains residual mean, standard
deviation, MAE, maximum absolute value, median, lag-one autocorrelation, and
positive/negative fractions.

## Optimization parity

When requested, P9 runs historical forecasts with optimization disabled and
enabled. Both paths must produce the same origin/target/position keys and
numerically equivalent predictions. Optimization drift is a formal failure.

## Argument and artifact evidence

Constructor-free API calls still use a no-silent-drop argument ledger. Unknown
`historical_forecasts`, `backtest`, or `residuals` arguments are rejected before
execution. Canonical SHA-256 values are produced for the policy and historical
record ledger.

## Verification boundary

P9 focused tests use a fake Darts-like runtime. They verify the contract, not
real `darts==0.46.1` execution, model accuracy, optimized-path equivalence, or
runtime residual behavior.
