# TEST_PLAN

## Local static tests

- compile every Python module;
- Ruff format/check;
- mypy on `src/loto/auto_campaign`;
- focused pytest suite in `tests/auto_campaign`;
- shell syntax checks;
- package installer idempotency test.

## P0 runtime tests

- version and signature capture;
- exact 32 common-argument signature comparison;
- dynamic BaseAuto subclass registry;
- false-positive count zero;
- default-config extraction for every model;
- complete registry/config SHA-256.

## P1 contract smoke

For each supported model/backend representative:

- import and instantiate;
- fit with validation;
- predict;
- persist every successful Trial;
- load Trial checkpoint and predict;
- save NeuralForecast bundle;
- load bundle and predict;
- shape, finite, equality, CUDA, GPU PID, and CPU-fallback checks.

## Formal stages

- Pairwise and domain coverage must report 100% planned coverage.
- HPO successful Trial count must equal persisted successful Trial count.
- Validation replay must use only the Validation partition.
- OOF endpoints must stay entirely inside Train.
- Holdout must contain exactly 20 chronological origins per model/track/seed.
- Prospective prediction files must have UTC freeze time and SHA-256.
- Baseline and AutoModel metrics must use the same origins.

## Final verification

`loto-auto-campaign verify` checks complete SHA listings, task counts, every
successful Trial checkpoint, selected-model bundles, load/predict equality,
finite predictions, and zero CPU fallback.
