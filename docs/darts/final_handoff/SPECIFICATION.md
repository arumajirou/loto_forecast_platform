# Specification

## Phase map

- P1: isolated notorch and torch package boundaries.
- P2: provider protocol and request/response schema.
- P3: runtime discovery and optional dependency retention.
- P4: TimeSeries adapters and game geometry.
- P5: nine Local statistical model contracts.
- P6: six Regression model and lag/covariate contracts.
- P7: ten Torch model, Lightning, CUDA, PID, and VRAM contracts.
- P8: four Foundation model, revision, artifact, and capability contracts.
- P9: historical forecasts, backtest, retrain, residual, and metric parity.
- P10: naive/regression ensemble and conformal calibration contracts.
- P11: save/load, clean save, checkpoint, weights, cross-device, and replay contracts.
- P12: eight-track cross-library fairness, deduplication, aggregation, and champion contracts.

## Required inputs

A run requires immutable raw data, chronological split definitions, seed and fold lists, game
positions, horizon, target and covariate lag definitions, covariate columns, provider and model
identity, package versions, code commit, and device request.

## Required prediction key

Every prediction is uniquely identified by provider execution, underlying algorithm,
canonical-execution flag, seed, fold, origin, target timestamp or index, position, and horizon
step. Comparison is rejected when providers do not have identical required keys.

## Required outputs

Store predictions, actuals when available, all metrics, baseline metrics, seed aggregates,
wrapper-versus-standalone deltas, failures, device evidence, persistence evidence, data/config/
code hashes, and the champion decision.

## Champion decision

Rank only canonical executions. A champion must beat the strongest complete baseline set on
mean Hit@±1 and must not underperform the strongest baseline on worst-seed Hit@±1. Otherwise
return `NO_CHAMPION`.

## Status classes

- `SUCCESS`: all requested real-runtime checks passed.
- `FAILED`: execution or certification failed with retained evidence.
- `DEPENDENCY_MISSING`: required package or model is unavailable.
- `CI_BLOCKED_PRE_RUN`: hosted CI ended before steps were created.
- `PARTIALLY_VERIFIED`: local contract checks passed while real-runtime gates remain pending.
