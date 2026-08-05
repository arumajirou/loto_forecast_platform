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
- Chronos2, TimesFM2p5, TiRex, and PatchTSTFM identities: PASS;
- stable capability-matrix SHA-256: PASS;
- immutable model revision and local-artifact manifest contract: PASS;
- variable input chunks and model-specific limits: PASS;
- TiRex license and partial-fine-tuning restrictions: PASS;
- runtime capability drift and unsupported-covariate rejection: PASS;
- zero-shot and fine-tuning runtime-evidence gates: PASS;
- package dependency failure retention: PASS;
- local, multivariate, and global-sequence fake-runtime paths: PASS;
- prediction shape, finite values, device evidence, and raw-frame immutability: PASS;
- compileall, AST parse, YAML/JSON parse, and line-length inspection: PASS.

Documented focused increment runs total 57 tests. They were not all executed together in
one environment, so this is not a single 57-test certification run.

## Blocked

- Ruff was unavailable from the configured package registry;
- `darts==0.46.1` and its optional Foundation dependencies were unavailable;
- notorch and torch lockfiles could not be generated;
- Chronos2 and TiRex revisions remain intentionally unresolved in example configs;
- no Foundation model download, local manifest, zero-shot, or fine-tuning run occurred;
- no real CUDA, persistence, accuracy, Holdout, or Prospective claim is made;
- GitHub Actions jobs continue to fail before step creation and produce no logs.
