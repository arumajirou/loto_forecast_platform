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
- cumulative focused Darts contract tests: 14 passed;
- Python compileall: PASS;
- Python AST parse: PASS;
- lines over repository 100-character limit: 0;
- chronological Train/Holdout isolation: PASS;
- Hit@±1, position-wise and all-position metrics: PASS;
- deterministic random/fixed/mean/median/last/frequency/seasonal baselines: PASS;
- fake-model save/load/re-predict equality: PASS;
- prospective SHA-256 tamper detection: PASS;
- manifest and portable SHA256SUMS verification: PASS;
- failed runtime certification evidence retention: implemented and unit covered.

## Blocked

- Ruff executable was absent and the configured package registry did not expose Ruff;
- `darts==0.46.1` was not available from the configured registry;
- GitHub tag dependency resolution failed;
- no environment `uv.lock` could be generated;
- real Darts discovery, fit, predict, persistence and GPU certification remain pending;
- GitHub Actions hosted jobs failed before step creation and produced no job logs.

No real Darts runtime or accuracy claim is inferred from fake-runtime tests.
