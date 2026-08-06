# OpenTelemetry Instrumentation v1 Test Plan

## Focused unit and integration tests

Required scenarios:

1. disabled tracing returns `NOT_CONFIGURED`;
2. enabled tracing rejects an unpinned service version;
3. enabled OTLP tracing without endpoint is blocked;
4. strict configuration rejects coercion, unsafe endpoint credentials and invalid batch geometry;
5. domain spans share trace and parent/child identity;
6. trace/span identity is bound to and restored from the telemetry context;
7. exception messages and stack traces are absent;
8. secret, protected-actual, nested and non-finite attributes are absent;
9. FastAPI middleware extracts propagation and reuses but does not generate request ID;
10. FastAPI spans omit raw path and query;
11. synchronous HTTPX propagates trace context;
12. asynchronous HTTPX exports a client span;
13. HTTPX spans omit raw path and query;
14. SQLAlchemy spans contain operation/system but no SQL or parameter values;
15. instrumentation is idempotent and reversible where applicable;
16. exporter failure becomes `DEGRADED`;
17. queue saturation drops without blocking the producer;
18. console exporter smoke succeeds;
19. HTTP OTLP protobuf bytes reach a loopback stub;
20. exporter acceptance does not become formal `VERIFIED`;
21. platform `FAILED`/`BLOCKED` maps to OpenTelemetry error status;
22. HTTP client 4xx maps to OpenTelemetry error status.

## Static checks

```text
Python AST parse
compileall
line length <=100
production secret-pattern scan
JSON manifest parse
SHA256SUMS verification
remote Git blob parity
```

## Repository checks

When a complete checkout and tools are available:

```bash
uv run ruff format --check src/loto/telemetry/otel tests/telemetry
uv run ruff check src/loto/telemetry/otel tests/telemetry
uv run mypy src/loto/telemetry/otel
uv run pytest -q tests/telemetry/test_telemetry_contract_v1.py \
  tests/telemetry/test_otel_instrumentation_v1.py
uv run python -m compileall -q src tests
uv run pytest -q
```

## Live checks deferred

- actual OpenTelemetry Collector;
- gRPC OTLP receiver;
- Grafana Alloy routing;
- Tempo persistence and query;
- Grafana trace display;
- trace-to-log correlation;
- target FastAPI application wiring;
- existing production HTTPX/SQLAlchemy callsite adoption;
- load/overhead and queue-memory budget.

A loopback HTTP server that accepts OTLP protobuf is a transport smoke only and must not be described as
a collector or Tempo certification.
