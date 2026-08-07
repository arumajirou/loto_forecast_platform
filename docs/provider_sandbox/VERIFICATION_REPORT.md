# Verification Report

## Result

```text
STATUS=PARTIALLY_VERIFIED
FOUNDATION_ONLY=true
FOCUSED_TESTS=28 passed
STATEMENT_COVERAGE=88%
REAL_KERNEL_ISOLATION=false
REAL_BUBBLEWRAP_EXECUTION=false
REAL_OCI_EXECUTION=false
SECURITY_CERTIFIED=false
RUNTIME_CERTIFIED=false
```

## Executed locally

- strict contract and negative validation suite;
- fixed argv and literal metacharacter behavior;
- fake child success, nonzero exit, timeout and output overflow;
- requested/effective verification states;
- atomic evidence bundle roundtrip and tamper rejection;
- CLI policy validation and test-only execution acknowledgment;
- focused pytest-cov.

## Pre-publication findings corrected

1. pytest's reserved `request` fixture name was replaced with `execution_request`.
2. strict JSON evidence loading was changed to duplicate-key parsing followed by Pydantic JSON-mode
   validation.
3. host-root read-only bind was removed from Bubblewrap construction; only explicit mounts remain.
4. Bubblewrap GPU requests now fail closed because environment filtering is not device isolation.
5. output capture was changed from unbounded `communicate()` memory collection to temporary-file
   monitoring with process-group termination.
6. effective mount verification now binds hashed source path identity.

## Not executed

- real Bubblewrap or rootless OCI process;
- kernel namespace, cgroup, seccomp, capability or LSM inspection;
- real GPU device isolation;
- provider migration or model runtime;
- Ruff and mypy when unavailable;
- full repository pytest without a complete checkout;
- Holdout, Prospective, Registry or Promotion operations.
