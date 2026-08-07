# Telemetry Contract v1 Verification Report

## Status

```text
PARTIALLY_VERIFIED
FOCUSED_TESTS_PASS
COMPILEALL_PASS
AST_JSON_PASS
SHA256_PASS
RUFF_BLOCKED_TOOL_UNAVAILABLE
MYPY_BLOCKED_TOOL_UNAVAILABLE
FULL_PYTEST_NOT_STARTED
CI_BLOCKED_RUNNER_START
```

## Repository and duplicate audit

```text
repository=arumajirou/loto_forecast_platform
default_branch=main
base_sha=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
head_branch=feat/telemetry-contract-v1
relation_before_final_evidence_update=ahead 14 / behind 0
```

Before branch creation, GitHub was checked for the same branch, same-purpose PRs and Issues, the
main evaluation/API/observability surfaces, PR #79, PR #121, PR #123, PR #124/#129, PR #127,
PR #131 and PR #138. No common `src/loto/telemetry` package or same-purpose implementation was
found. PR #131 is the documentation-only design source and names this PR as Phase 2. PR #79 is
stale harness-specific observability and was not copied or modified.

## Changed scope

```text
src/loto/telemetry/__init__.py
src/loto/telemetry/buffer.py
src/loto/telemetry/codec.py
src/loto/telemetry/context.py
src/loto/telemetry/contracts.py
src/loto/telemetry/factory.py
src/loto/telemetry/metrics.py
src/loto/telemetry/redaction.py
tests/telemetry/test_telemetry_contract_v1.py
docs/telemetry/TELEMETRY_CONTRACT.md
docs/telemetry/TEST_PLAN.md
docs/telemetry/VERIFICATION_REPORT.md
docs/telemetry/ARTIFACT_MANIFEST.json
docs/telemetry/SHA256SUMS
```

No root dependency, `uv.lock`, workflow, FastAPI route, PR #127 health/readiness implementation,
OpenTelemetry exporter, Prometheus collector, model provider, Runtime Certification, Data Access
Ledger, evaluation protocol, custom UI, Holdout or Prospective path is changed.

## Executed verification

Environment:

```text
Python=3.13.5
pytest=9.0.2
pydantic=2.13.4
```

Executed in a dependency-light source mirror:

```text
focused pytest=25 passed
compileall=PASS
AST parse=PASS
JSON manifest parse=PASS
line length above 100 characters=0
secret-pattern scan=PASS
SHA256SUMS verification=PASS
remote source/test Git blob parity=PASS
```

Published source and focused-test blob parity:

```text
src/loto/telemetry/__init__.py=58ce9993580653bc238715fdca795a935e53dfa7
src/loto/telemetry/buffer.py=5cd69a1ee47a394bd4c058220670d5c405c1ea19
src/loto/telemetry/codec.py=ea0fba2be9204944953d71abac0d6cdfd3da69bf
src/loto/telemetry/context.py=ca420411da586d781fc4960c237dff59611182c5
src/loto/telemetry/contracts.py=7b97d215b773e62860ecde9d40b7d0b0d161ccc3
src/loto/telemetry/factory.py=bf6e71cde35db650d601223677d3d7d0b2921228
src/loto/telemetry/metrics.py=4e75ff322b6026fb41e33725dea36e77decc48ed
src/loto/telemetry/redaction.py=15c0b698b39d40e98424da6012a17f937f96a9e6
tests/telemetry/test_telemetry_contract_v1.py=ba1435677db3a3704a3ebea4409464e87f48d5a0
```

The first focused run found a `TypeError` when a direct unredacted actual list reached the
redaction-state validator. The validator was changed to compare safely and to evaluate protected
actuals with the complete event `reveal_state`. Nested secret validation and an authorized-reveal
regression were added. The full focused suite was rerun and all 25 tests passed. The failed first
run is retained here and is not hidden.

## Contract coverage

- strict frozen event envelope and bounded enums;
- UTC timestamps and safe correlation identifiers;
- contextvars-based nested context restoration;
- recursive secret, DSN, URI, bearer and query redaction;
- protected actual redaction before reveal;
- explicit already-authorized reveal state without granting authorization;
- no exception-message retention;
- bounded attributes and finite JSON values;
- deterministic canonical JSON and SHA-256;
- exporter-neutral metric definitions and finite label allowlists;
- prohibited high-cardinality labels;
- non-waiting bounded buffer with `DROPPED` versus `BLOCKED` outcomes.

## Pending and blocked verification

```text
Hypothesis=BLOCKED_TOOL_UNAVAILABLE
Ruff=BLOCKED_TOOL_UNAVAILABLE
mypy=BLOCKED_TOOL_UNAVAILABLE
existing observability/API regression=PENDING_COMPLETE_PRIVATE_CHECKOUT
full pytest=NOT_STARTED
```

GitHub Actions evidence on implementation head `3c26da2d20db65aa89c6544c18821c1adb47bae8`:

```text
workflow=ci
run_id=31084353819
run_number=2966
job=test
job_id=92560204195
conclusion=failure
recorded_steps=0
steps=[]
logs_url=null
classification=CI_BLOCKED_RUNNER_START
code_test_failure=NOT_DEMONSTRATED
```

Checkout, Python setup, dependency installation, Ruff, compileall, mypy and pytest did not start.

Property invariants are covered by deterministic generated loops because Hypothesis is unavailable in
the authoring environment. This is not represented as Hypothesis execution.

## Explicit non-claims

```text
existing JSONL writers migrated=false
PR #127 request ID integrated=false
OpenTelemetry installed or configured=false
OTLP export tested=false
Prometheus collectors registered=false
Grafana/Loki/Tempo/Alloy deployed=false
MLflow integrated=false
model or API instrumentation added=false
required-audit caller gate wired=false
Holdout accessed=false
Prospective accessed=false
protected-actual reveal authorized by this package=false
production deployment=false
merge readiness=false
```

## Rollback

Before merge, close the Draft PR. After merge, revert normally. The change is add-only and introduces
no dependency, lockfile, workflow, database, data or historical-artifact migration.

## Next PR

```text
feat/otel-instrumentation-v1
```
