# Data contract

## Raw data

Raw source data is immutable. Any derived table must record its source hash and transformation
configuration. Missing, duplicate, non-finite, or out-of-order records are rejected before
model execution.

## Canonical long-form fields

- series or game identifier;
- draw or timestamp index;
- position identifier such as `N1`;
- integer target value `y`;
- declared past, future, and static covariates;
- source-data SHA-256.

## Game geometry

Position names and order are explicit. Draw numbers must be integer, unique, increasing, and
gap-free where the source contract requires contiguous draws. Predictions must contain the
configured number of positions and horizon steps.

## Chronological partitions

Train precedes Validation, Validation precedes Holdout, and Holdout precedes Prospective.
Calibration and evaluation partitions used by conformal or stacking workflows must be
non-overlapping and ordered. No fit operation may use Holdout or Prospective observations.

## Lag and covariate safety

Target and past-covariate lags must reference history only. Future covariates may extend into
the forecast horizon only when declared by the model capability contract. Target position
columns cannot be reused as covariates. Coverage must extend through every requested target,
shift, and future lag.

## Prediction record

A prediction record contains run ID, provider execution, algorithm identity, seed, fold,
origin, target index or timestamp, position, horizon step, predicted value, actual value when
available, device evidence reference, and prediction SHA-256.

## Prospective seal

Before actual values are known, serialize the complete prospective prediction payload in
canonical order, record UTC time, and compute SHA-256. Verification after disclosure must
recompute the same digest before attaching actuals and metrics.
