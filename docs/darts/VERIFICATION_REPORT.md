# Darts first-increment verification report

## Status

`PARTIALLY_VERIFIED / LOCAL_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

## Executed

- branch scope designed from frozen `main` SHA;
- Python compileall: PASS;
- focused pytest: 10 passed;
- Python AST parse: PASS, 13 files;
- lines over repository 100-character limit: 0;
- raw-input immutability test: PASS;
- fake-runtime current-ensemble reproduction: PASS;
- simple secret-pattern scan: PASS.

## Blocked

- Ruff executable was absent and the configured package registry did not expose Ruff;
- `darts==0.46.1` was not available from the configured registry;
- GitHub tag dependency resolution failed;
- no environment `uv.lock` could be generated;
- real Darts discovery, fit, predict, persistence and GPU certification remain pending.

No runtime or accuracy claim is inferred from the fake-runtime unit tests.
