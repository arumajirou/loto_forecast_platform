# P5 local statistical model contract

**Status:** `LOCAL_CONTRACT_VERIFIED / REAL_DARTS_RUNTIME_PENDING`

## Candidate set

The first native local-model matrix contains exactly these campaign identities:

- NaiveMean
- NaiveSeasonal
- NaiveDrift
- NaiveMovingAverage
- ARIMA
- AutoARIMA
- ExponentialSmoothing
- Theta
- Croston

This list is a campaign scope, not a claim that every class imports or executes in the
current environment. Runtime discovery remains authoritative. Missing optional dependencies
produce explicit rows and never reduce the denominator silently.

## Fair execution

Every candidate receives the same position-local panel, horizon, chronological folds, seed
set, and evaluation policy. Constructor, fit, and predict arguments are checked against the
runtime signatures. Unknown arguments fail closed. One model failure does not stop the
remaining candidates.

Campaign minimum-history thresholds are policy safeguards rather than upstream Darts API
claims. They are evaluated before model construction and exclude Holdout rows from fitting.

## Duplicate accounting

AutoARIMA and other wrapped statistical implementations must retain their actual provider
identity. Darts-native/wrapper results are not counted as independent evidence against a
standalone StatsForecast result unless the estimator, arguments, folds, and provider are
reported separately.

## Acceptance gate

A successful import or point prediction does not make a champion. Formal adoption requires
identical multi-seed OOF folds and comparison against Random, fixed, mean, median, last,
frequency, seasonal/statistical baselines. The primary metric remains Hit@±1, with MAE,
MSE, RMSE, position-wise Hit@±1, all-position Hit@±1, variance, and worst seed retained.

## Current certification boundary

The focused tests use fake Darts model and TimeSeries classes. They verify matrix coverage,
argument rejection, shape/finite checks, failure retention, and raw-frame immutability.
They do not certify Darts 0.46.1 imports, statistical correctness, real save/load behavior,
or accuracy improvement.
