# Architecture

## Layer 1: immutable data and provenance

Raw data is never overwritten. A provenance record binds the data hash, configuration hash,
code hash, Git commit, provider/model identity, revision, seeds, folds, and run ID.

## Layer 2: provider-neutral contracts

Pydantic schemas define requests, game geometry, chronological partitions, lags, covariates,
metrics, device evidence, persistence evidence, and cross-library fairness. Invalid or unknown
fields fail closed.

## Layer 3: Darts family adapters

Separate adapters cover Local, Regression, Torch, Foundation, Ensemble, and Conformal model
families. Optional dependencies and unsupported capabilities remain visible as failures rather
than silently removing models.

## Layer 4: execution and certification

Execution produces prediction records and runtime evidence. Certification verifies complete
keys, finite output, shape, chronological isolation, device use, save/load replay, metric
parity, conformal intervals, and SHA-256 integrity.

## Layer 5: cross-library comparison

Darts native and wrapper paths are compared with standalone NeuralForecast, MLForecast,
StatsForecast, AutoGluon, and direct Foundation providers. Execution identity and underlying
algorithm identity are separate so wrapper experiments remain visible without duplicate
algorithm ranking.

## Layer 6: reports and handoff

Reports contain per-seed and aggregate metrics, baseline gates, failure tables, and the final
champion decision. The deterministic final package contains the 12 handoff documents and
verified checksums.
