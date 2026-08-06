# OpenTelemetry Instrumentation v1 Verification Report

## Status

```text
PARTIALLY_VERIFIED
STACKED_ON_PR_141
FOCUSED_TESTS_PASS
COMPILEALL_PASS
AST_PASS
LINE_LENGTH_PASS
PRODUCTION_SECRET_SCAN_PASS
OTLP_HTTP_LOOPBACK_STUB_PASS
RUFF_BLOCKED_TOOL_UNAVAILABLE
MYPY_BLOCKED_TOOL_UNAVAILABLE
FULL_PYTEST_NOT_STARTED
LIVE_COLLECTOR_NOT_PROBED
APPLICATION_WIRING_DEFERRED
```

## Repository and stacking audit

```text
repository=arumajirou/loto_forecast_platform
default_branch=main
main_sha=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
stack_base_pr=141
stack_base_branch=feat/telemetry-contract-v1
stack_base_sha=0caa8e7fc86f49ffa953cd3e5f9867bf82d6b9ac
head_branch=feat/otel-instrumentation-v1
```

GitHub was rechecked before branch creation for the same branch, same-purpose open/closed PRs and Issues,
OpenTelemetry code and dependencies, PR #127, PR #131 and PR #141. No same-purpose implementation was
found.

PR #141 is open, Draft and mergeable and owns the strict event, context and redaction contracts consumed
by this PR. This PR is therefore stacked on PR #141 instead of duplicating those files from `main`.

## Changed scope

```text
src/loto/telemetry/otel/__init__.py
src/loto/telemetry/otel/asgi.py
src/loto/telemetry/otel/config.py
src/loto/telemetry/otel/exporters.py
src/loto/telemetry/otel/httpx_instrumentation.py
src/loto/telemetry/otel/processor.py
src/loto/telemetry/otel/sqlalchemy_instrumentation.py
src/loto/telemetry/otel/tracing.py
tests/telemetry/test_otel_instrumentation_v1.py
docs/otel/INSTRUMENTATION_CONTRACT.md
docs/otel/UPSTREAM_FACTCHECK.md
docs/otel/TEST_PLAN.md
docs/otel/RUNBOOK.md
docs/otel/VERIFICATION_REPORT.md
docs/otel/ARTIFACT_MANIFEST.json
docs/otel/SHA256SUMS
```

No file owned by PR #141 is modified. No `pyproject.toml`, `uv.lock`, workflow, FastAPI application,
request-ID middleware, Prometheus collector, model provider, evaluation, Runtime Certification, Data
Access Ledger, Holdout or Prospective path is changed.

## Dependency audit

The existing `full` extra already declares FastAPI, HTTPX, SQLAlchemy, OpenTelemetry SDK and OTLP exporter
requirements. No new dependency is introduced.

The optional implementation is isolated under `loto.telemetry.otel`; the base `loto.telemetry` package is
not changed to import optional runtime dependencies.

## Upstream fact check

Primary OpenTelemetry Python and semantic-convention sources were reviewed on 2026-08-06.

Important finding:

```text
BatchSpanProcessor.export_timeout_millis is present but current Python source says it is not used.
```

The implementation therefore does not claim that argument supplies a hard deadline. It uses:

- a platform-owned non-blocking bounded queue;
- explicit queue-drop counters;
- bounded caller-side force-flush wait;
- the OTLP exporter's network timeout;
- daemon-worker shutdown that does not wait indefinitely for a non-compliant injected exporter.

Current database attribute names `db.system.name` and `db.operation.name` are used. Generic raw HTTP paths,
queries and full URLs are intentionally omitted under the platform privacy policy.

## Executed environment

```text
Python=3.13.5
pytest=9.0.2
pydantic=2.13.4
opentelemetry-api=1.42.1
opentelemetry-sdk=1.42.1
opentelemetry-exporter-otlp=1.42.1
httpx=0.28.1
sqlalchemy=2.0.50
fastapi=0.128.2
starlette=0.50.0
```

The local FastAPI/Starlette versions are not the repository's exact locked resolution. The ASGI smoke is
therefore compatibility evidence, not a complete lockfile validation.

## Focused verification

Final run:

```text
focused pytest=16 passed
compileall=PASS
AST parse=PASS
new code/test line length >100=0
production secret-pattern scan=PASS
console exporter smoke=PASS
in-memory exporter smoke=PASS
OTLP HTTP protobuf loopback stub=PASS
FastAPI ASGI trace smoke=PASS
HTTPX sync trace and propagation smoke=PASS
HTTPX async trace smoke=PASS
SQLAlchemy operation trace smoke=PASS
queue saturation non-blocking drop smoke=PASS
export failure degradation smoke=PASS
```

The HTTP loopback endpoint only accepted OTLP protobuf bytes and returned HTTP 200. It was not an
OpenTelemetry Collector, Alloy, Tempo or Grafana certification.

## Hardening history

The first implementation used the SDK `BatchSpanProcessor`. Upstream source review showed that its
`export_timeout_millis` parameter is currently not used. The implementation was replaced with an
application-owned bounded processor so queue drops are observable and producer calls remain non-blocking.

After changing success semantics from `VERIFIED` to `NOT_PROBED / export_accepted_unverified`, four tests
failed because they still expected the old status. The expectations were corrected, unpinned-version and
queue-saturation regressions were added.

A final concurrency review then moved queue insertion and pending-count updates under the same condition
lock, preventing a fast exporter from decrementing pending before the producer records acceptance. Domain
spans now map platform `FAILED`/`BLOCKED` to OpenTelemetry error status, and HTTP client 4xx responses are
marked as errors. The complete final suite passed 16 tests.

## Pending and blocked verification

```text
Ruff=BLOCKED_TOOL_UNAVAILABLE
mypy=BLOCKED_TOOL_UNAVAILABLE
PR_141_focused_regression=PENDING_COMPLETE_PRIVATE_CHECKOUT
FastAPI_locked_version_regression=PENDING_COMPLETE_PRIVATE_CHECKOUT
full pytest=NOT_STARTED
real OpenTelemetry Collector=NOT_PROBED
OTLP gRPC live receiver=NOT_PROBED
Alloy routing=NOT_PROBED
Tempo persistence/query=NOT_PROBED
Grafana trace display=NOT_PROBED
trace-to-log correlation=NOT_PROBED
actual src/loto/api/app.py wiring=DEFERRED
production HTTPX callsite wiring=DEFERRED
production SQLAlchemy engine wiring=DEFERRED
load and overhead budgets=NOT_MEASURED
```

None of these items is represented as PASS.

## Explicit non-claims

```text
PR #141 merged=false
PR #127 integrated=false
global tracer provider installed=false
application instrumentation enabled by default=false
collector configured=false
collector ready=false
Tempo persistence verified=false
Grafana trace query verified=false
raw HTTP paths exported=false
SQL statements exported=false
protected actuals exported=false
production deployment=false
merge readiness=false
```

## Rollback

Before merge, close this stacked Draft PR. After merge, revert normally. No dependency, lockfile, workflow,
database, data, deployment or historical-artifact migration exists.

## Next PR

```text
feat/platform-metrics-v1
```

Do not start the next integration PR as though this stack were merged. Re-audit and preserve stacking or
wait for prerequisite integration.
