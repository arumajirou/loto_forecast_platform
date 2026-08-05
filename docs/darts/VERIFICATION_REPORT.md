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
- Python compileall: PASS;
- chronological Train/Holdout isolation: PASS;
- Hit@±1, position-wise and all-position metrics: PASS;
- deterministic random/fixed/mean/median/last/frequency/seasonal baselines: PASS;
- fake-model save/load/re-predict equality: PASS;
- prospective SHA-256 tamper detection: PASS;
- manifest and portable SHA256SUMS verification: PASS.

## Third increment

- focused OOF/multi-seed/provenance tests: 6 passed;
- expanding chronological folds: PASS;
- Train/Validation adjacency and non-overlap: PASS;
- source-frame immutability under evaluator mutation: PASS;
- identical fold coverage required for every seed: PASS;
- mean, population variance, and worst-seed retention: PASS;
- best-seed-only adoption rejection: PASS;
- baseline mean/worst Hit@±1 gate: PASS;
- `NO_CHAMPION` fail-closed outcome: implemented and unit covered;
- data/config/code SHA-256 tamper sensitivity: PASS;
- Python compileall and AST parse for third-increment files: PASS;
- lines over repository 100-character limit in third-increment files: 0;
- YAML configuration parse: PASS;
- latest GitHub Actions run 30980565162: BLOCKED_PRE_RUN with steps=null.

## Blocked

- Ruff executable was absent and the configured package registry did not expose Ruff;
- `darts==0.46.1` was not available from the configured registry;
- GitHub tag dependency resolution failed;
- no environment `uv.lock` could be generated;
- real Darts discovery, OOF fit/predict, persistence and GPU certification remain pending;
- GitHub Actions hosted jobs failed before step creation and produced no job logs.

No real Darts runtime or accuracy claim is inferred from fake-runtime and contract tests.
