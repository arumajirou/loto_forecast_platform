# Verification Report

Verification date: 2026-08-06 JST

```text
STATUS=PARTIALLY_VERIFIED
STATIC_DATA_ACCESS_LEDGER_IMPLEMENTED
FOCUSED_TESTS_PASS
PIPELINE_INTEGRATION_PENDING
REAL_DATA_ACCESS_NOT_EXECUTED
```

## Completed locally

- focused pytest: 41 passed
- package/test compileall: PASS
- AST parse of changed Python: PASS
- example JSON parse: PASS
- CLI smoke against example ledger: exit 0 / PASS
- line-length scan (>100): PASS at report generation time
- secret-pattern scan: PASS at report generation time
- artifact SHA256SUMS verification: PASS at report generation time

## Not verified as PASS

- Ruff: unavailable in the local execution environment
- mypy: unavailable in the local execution environment
- related repository-wide leakage tests: not executed
- full repository pytest: not executed
- GitHub Actions: `CI_BLOCKED_RUNNER_START`; jobs ended before recording any step and logs returned
  `BlobNotFound`

No check listed as unavailable or unexecuted is represented as PASS.
