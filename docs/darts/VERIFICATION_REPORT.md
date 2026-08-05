# Darts verification report

## Status

`PARTIALLY_VERIFIED / LOCAL_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

## P1-P4 foundation

- initial focused tests: 10 passed;
- protocol, discovery, argument ledger, GameGeometry, and adapters: PASS;
- current RegressionEnsembleModel fake-runtime reproduction: PASS.

## Evaluation and persistence increment

- focused tests: 4 passed;
- Train/Holdout isolation and Hit@±1 metric family: PASS;
- deterministic baseline family: PASS;
- save/load/re-predict and Prospective SHA-256 contracts: PASS.

## OOF, multi-seed, and provenance increment

- focused tests: 6 passed;
- chronological folds, identical seed coverage, mean/variance/worst retention: PASS;
- best-seed-only rejection, baseline gate, and `NO_CHAMPION`: PASS;
- data/config/code hash tamper sensitivity: PASS.

## P5 Local statistical increment

- focused tests: 6 passed;
- nine identities, missing-dependency retention, argument rejection: PASS;
- per-model isolation, finite shape, and raw-frame immutability: PASS.

## P6 Regression increment

- focused tests: 8 passed;
- six identities, lags/covariates, local/global paths: PASS;
- estimator identity, dependency retention, and MLForecast parity SHA-256: PASS.

## P7 Torch increment

- focused tests: 11 passed;
- ten identities, shared training, local/global fake-runtime paths: PASS;
- CUDA parameter/prediction devices, GPU PID, and memory evidence: PASS_CONTRACT;
- CPU fallback, accelerator mismatch, and dependency failure retention: PASS.

## P8 Foundation increment

- focused tests: 12 passed;
- four identities and stable capability-matrix SHA-256: PASS;
- immutable revision, artifact manifest, limits, and TiRex restrictions: PASS;
- capability drift, zero-shot, and fine-tuning evidence gates: PASS;
- fake-runtime layouts, finite predictions, device evidence, immutability: PASS.

## P9 Historical evaluation increment

- focused tests: 12 passed;
- complete chronological origins and exact forecast-key coverage: PASS;
- boolean/integer retrain schedules and prefit evidence: PASS;
- Hit@±1, position Hit@±1, all-position Hit@±1, MAE, MSE, RMSE: PASS;
- Darts backtest MAE/MSE/RMSE parity and mismatch rejection: PASS_CONTRACT;
- residual sign, order, shape, and numeric parity: PASS_CONTRACT;
- optimized/general historical forecast parity: PASS_CONTRACT;
- API argument ledger and policy/record SHA-256: PASS;
- source-frame immutability: PASS;
- compileall, AST parse, YAML parse, and line-length inspection: PASS.

## P10 Ensemble and conformal increment

- focused tests: 12 passed;
- four ensemble/conformal identities and stable identity SHA-256: PASS;
- Train/calibration/evaluation partition order and non-overlap: PASS;
- pre-fitted global-model, availability, shift, and likelihood rules: PASS;
- scoped constructor/fit/predict no-silent-drop ledger: PASS;
- naive arithmetic-mean parity and finite shape checks: PASS;
- stacking key completeness, seed/fold coverage, and leakage rejection: PASS;
- quantile validation, non-crossing, and base-median parity: PASS;
- nominal/empirical coverage, interval width, position and all-position metrics: PASS;
- matrix-level failure retention and raw-frame immutability: PASS;
- canonical SHA-256 stability and tamper sensitivity: PASS;
- compileall, AST parse, YAML parse, and line-length inspection: PASS.

## P11 persistence and GPU increment

- focused tests: 13 passed;
- exact six-family persistence coverage: PASS;
- process-terminated save/load and disk reload: PASS_CONTRACT;
- artifact size and SHA-256 integrity: PASS;
- model identity, shape, finite, and numerical prediction replay: PASS;
- global clean-save state removal: PASS;
- Torch companion weight artifact requirement: PASS;
- best and last checkpoint trainer/optimizer/scheduler restoration: PASS_CONTRACT;
- initialized-model weights and encoder restoration: PASS_CONTRACT;
- CPU and CUDA `map_location` device certification: PASS_CONTRACT;
- GPU PID, VRAM, allocated/reserved memory, and CPU fallback rejection: PASS_CONTRACT;
- argument ledger, matrix failure retention, and evidence SHA-256: PASS;
- compileall, AST parse, YAML/JSON parse, and line-length inspection: PASS.

## P12 cross-library comparison increment

- focused tests: 14 passed;
- all eight execution tracks and wrapper/standalone identity rules: PASS;
- immutable versions, base revisions, and SHA-256 validation: PASS;
- common data/split/fold/seed/lag/covariate/Train-only fitting contract: PASS;
- target leakage and target-as-covariate rejection: PASS;
- one canonical execution per duplicated base algorithm: PASS;
- GPU effective-device, PID, VRAM, and CPU-fallback rejection: PASS_CONTRACT;
- exact prediction-key and complete position coverage parity: PASS;
- Hit@±1 metric family, MAE, MSE, RMSE, seed mean/variance/worst: PASS;
- wrapper prediction/metric delta reporting without algorithm double counting: PASS;
- strict wrapper parity option and prediction-drift rejection: PASS;
- canonical-only seven-baseline champion gate: PASS;
- provider failure retention and report SHA-256 tamper sensitivity: PASS;
- compileall, AST parse, YAML parse, and line-length inspection: PASS.

Documented focused increment runs total 108 tests. They were not all executed together in
one environment, so this is not a single 108-test certification run.

## Blocked

- Ruff was unavailable from the configured package registry;
- `darts==0.46.1` and optional dependencies were unavailable;
- notorch and torch lockfiles could not be generated;
- Chronos2 and TiRex revisions remain intentionally unresolved in example configs;
- no real Foundation, historical, ensemble/conformal, or persistence runtime occurred;
- no real checkpoint, weights, cross-device, GPU PID, VRAM, or replay result exists;
- no real Darts/NeuralForecast/MLForecast/StatsForecast/AutoGluon comparison occurred;
- no real wrapper parity, deduplicated ranking, or cross-library champion exists;
- no real CUDA, persistence, accuracy, Holdout, or Prospective claim is made;
- GitHub Actions jobs continue to fail before step creation and produce no logs.
