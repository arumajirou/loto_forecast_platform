# Darts verification report

## Status

`PARTIALLY_VERIFIED / LOCAL_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

## First increment

- Python compileall: PASS;
- focused pytest: 10 passed;
- Python AST parse: PASS, 13 files;
- lines over repository 100-character limit: 0;
- raw-input immutability test: PASS;
- fake-runtime current-ensemble reproduction: PASS;
- simple secret-pattern scan: PASS.

## Second increment

- focused evaluation/certification tests: 4 passed;
- cumulative focused Darts contract tests at that increment: 14 passed;
- chronological Train/Holdout isolation: PASS;
- Hit@±1, position-wise and all-position metrics: PASS;
- deterministic random/fixed/mean/median/last/frequency/seasonal baselines: PASS;
- fake-model save/load/re-predict equality: PASS;
- prospective SHA-256 tamper detection: PASS;
- manifest and portable SHA256SUMS verification: PASS.

## Third increment

- focused OOF/multi-seed/provenance tests: 6 passed;
- expanding chronological folds and non-overlap: PASS;
- identical fold coverage required for every seed: PASS;
- mean, population variance, and worst-seed retention: PASS;
- best-seed-only adoption rejection: PASS;
- baseline mean/worst Hit@±1 gate and `NO_CHAMPION`: PASS;
- data/config/code SHA-256 tamper sensitivity: PASS.

## P5 Local statistical increment

- focused Local statistical matrix tests: 6 passed;
- nine required identities and missing-dependency retention: PASS;
- constructor/fit/predict no-silent-drop rule: PASS;
- per-model failure isolation and finite shape checks: PASS;
- source-frame immutability: PASS.

## P6 Regression increment

- focused Regression contract tests: 8 passed;
- six required Regression identities: PASS;
- negative target/past lag enforcement: PASS;
- future-covariate horizon coverage: PASS;
- likelihood/quantile consistency: PASS;
- `SKLearnModel` estimator identity/factory contract: PASS;
- position-local and global-sequence fake-runtime execution: PASS;
- dependency/runtime failure retention: PASS;
- unknown argument rejection: PASS;
- prediction position/horizon/finite validation: PASS;
- raw target-frame immutability: PASS;
- MLForecast parity SHA-256 stability and tamper sensitivity: PASS;
- compileall, AST parse, YAML parse, and 100-character line inspection: PASS.

## P7 Torch increment

- focused Torch contract tests: 10 passed;
- ten required Torch identities: PASS;
- shared chunk/epoch/batch/seed/Lightning trainer contract: PASS;
- serialized `max_gpu_jobs=1` policy: PASS;
- runtime object identity resolver requirement: PASS;
- position-local and global-sequence fake-runtime execution: PASS;
- CUDA parameter/prediction device evidence checks: PASS;
- GPU PID and VRAM/CUDA-memory evidence requirements: PASS;
- CPU fallback rejection with retained evidence: PASS;
- per-model dependency/runtime failure isolation: PASS;
- prediction shape/finite and raw-frame immutability: PASS;
- compileall, AST parse, YAML/JSON parse, and line-length checks: PASS.

## Blocked

- Ruff executable was absent and the configured package registry did not expose Ruff;
- `darts==0.46.1` was not available from the configured registry;
- GitHub tag dependency resolution failed;
- no environment `uv.lock` could be generated;
- real Darts Local/Regression/Torch execution, OOF, persistence, and GPU certification
  remain pending;
- the latest GitHub Actions failure is not treated as a code failure without usable step logs.

No real Darts runtime or accuracy claim is inferred from fake-runtime and contract tests.
