# Runtime Certification SDK Foundation Verification Report

## Status

```text
PARTIALLY_VERIFIED
SDK_FOUNDATION_IMPLEMENTED
ORIGINAL_FAKE_PROVIDER_FOCUSED_TESTS_PASS
PROCESS_AND_ARTIFACT_SECURITY_HARDENING_APPLIED
SECURITY_REGRESSION_TESTS_PASS
PYTHON_COMPILE_PASS
REAL_PROVIDER_MIGRATION_NOT_PERFORMED
REAL_GPU_EXECUTION_NOT_PERFORMED
ACCURACY_NOT_EVALUATED
FULL_REPOSITORY_VALIDATION_PENDING
MERGE_NOT_PERFORMED
```

## Repository state

- default branch: `main`;
- audited main SHA: `239601723177636f6d566cbc89fc0812f69d8db3`;
- working branch: `agent/runtime-certification-sdk-foundation-v1`;
- original foundation head: `beb38810926428322709530fd393d060701d8dd6`;
- patched security-test head before documentation-only updates:
  `22176d16d59b2b9df0f47d830ace886d543cff49`.

No existing common runtime-certification SDK was present on the audited default branch. The audit
identified repeated implementations in Chronos-2, TimesFM 2.5, Moirai 2.0, TiRex-2, Toto 2.0,
Sundial, TabPFN-TS, NeuralForecast, Merlion and StatsForecast.

## Added scope

```text
src/loto/runtime_certification/__init__.py
src/loto/runtime_certification/artifacts.py
src/loto/runtime_certification/contracts.py
src/loto/runtime_certification/device_evidence.py
src/loto/runtime_certification/identity.py
src/loto/runtime_certification/output_validation.py
src/loto/runtime_certification/replay.py
src/loto/runtime_certification/statuses.py
src/loto/runtime_certification/subprocess_runner.py
src/loto/runtime_certification/verifier.py
tests/runtime_certification/test_sdk_foundation.py
tests/runtime_certification/test_sdk_security_regressions.py
docs/runtime_certification/ARCHITECTURE.md
docs/runtime_certification/DATA_CONTRACT.md
docs/runtime_certification/TEST_PLAN.md
docs/runtime_certification/VERIFICATION_REPORT.md
docs/runtime_certification/MIGRATION_CHECKLIST.md
```

No provider, root dependency, lockfile, workflow, shared catalog, model worker, raw data, prediction,
Holdout or Prospective path is changed.

## Security hardening applied

1. Artifact identities reject C0 and DEL control characters before line-based manifest generation.
2. ZIP verification rejects control characters in member names.
3. The real subprocess executor records the started provider PID.
4. Real evidence requires an observed execution PID.
5. Execution PID must equal the device-evidence provider PID whenever a PID is present.
6. An observation loader cannot replace the executor-owned `ProcessExecution` value.

These changes close evidence-splicing and manifest-name ambiguity paths without migrating or enabling
any provider.

## Executed validation

Original foundation evidence recorded on head
`beb38810926428322709530fd393d060701d8dd6`:

```text
focused pytest=14 passed
Python compileall=PASS
Python AST parse=PASS
provider-specific import scan=PASS
```

Independent reconstruction of the patched source and the new security regression file:

```text
AST parse=PASS
compileall=PASS
security regression pytest=7 passed in 0.76s
real CPU compatibility smoke=PASS
Python lines over 100 characters=0
```

The seven new regression cases cover three unsafe artifact-path variants, one unsafe ZIP member,
real subprocess PID capture, PID/device binding, and executor-evidence replacement rejection.

The tests use no CUDA and no real model provider. They validate SDK behavior only.

## GitHub Actions evidence

```text
workflow run=31141143480
job=92751121221
conclusion=failure
executed steps=[]
classification=CI_BLOCKED_PRE_RUN
```

No checkout, Ruff, mypy, compile, or pytest step executed. This is infrastructure/control-plane
evidence and is not represented as a repository-code test failure.

## Pending validation

| Validation | Status | Reason |
|---|---|---|
| Focused tests in complete private checkout | PENDING | Current connector has no checkout execution surface |
| Full repository compileall | PENDING | Complete checkout was unavailable |
| Full repository pytest | PENDING | Deferred until a runnable repository environment exists |
| Ruff | UNAVAILABLE | Ruff executable unavailable in the independent environment |
| mypy | UNAVAILABLE | mypy executable unavailable in the independent environment |
| Self-hosted workflow on patched head | PENDING | `workflow_dispatch` is not exposed by this connector |
| Real CPU provider adapter | PENDING | Provider migration is intentionally separate |
| Real GPU formal run | PENDING | Prohibited from this foundation PR |

Unavailable checks are not represented as PASS.

## Non-claims

- no existing provider uses this SDK yet;
- no package installation or model load occurred;
- no real CPU or GPU provider certification run occurred;
- no real GPU UUID, VRAM or PID-release evidence was collected;
- no save/reload/re-predict was performed with a real model;
- no Hit@±1, MAE, MSE, RMSE or baseline comparison was computed;
- no OOF, Holdout, Prospective, promotion or production certification occurred.

## Safety

- no direct write to main;
- no force push or history rewrite;
- no Ready transition;
- no merge or auto-merge;
- no provider bulk migration;
- no root dependency or `uv.lock` change.
