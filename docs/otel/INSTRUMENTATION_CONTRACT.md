# OpenTelemetry Instrumentation v1 Contract

## Status

```text
STACKED_ON_PR_141
EXPORTER_INTEGRATION_FOUNDATION
APPLICATION_WIRING_DEFERRED
LIVE_COLLECTOR_NOT_CERTIFIED
```

## Scope

This increment implements OpenTelemetry trace construction and transport-boundary helpers on top of the
strict telemetry contract introduced by PR #141. It does not replace that contract, install a global
tracer provider, create Prometheus collectors, deploy a collector, or modify the FastAPI application.

The optional package is:

```text
loto.telemetry.otel
```

Importing `loto.telemetry` remains independent of the optional OpenTelemetry, FastAPI, HTTPX and
SQLAlchemy runtime dependencies.

## Dependency boundary

The existing repository `full` extra already declares:

```text
fastapi
httpx
sqlalchemy
opentelemetry-sdk
opentelemetry-exporter-otlp
```

This PR therefore adds no dependency and does not modify `pyproject.toml` or `uv.lock`. Runtime users of
`loto.telemetry.otel` must install the `full` extra. A dedicated dependency extra can be considered only
in a separate dependency-and-lock PR.

## Configuration

`TracingConfig` is strict, frozen and fail-closed. Fields:

```text
enabled
service_name
service_version
environment
otlp_endpoint
otlp_protocol
export_timeout_seconds
batch_queue_size
batch_size
sample_ratio
resource_attributes
instrument_fastapi
instrument_httpx
instrument_sqlalchemy
```

Rules:

- tracing is disabled by default;
- enabled tracing rejects `service_version=UNPINNED`;
- enabled OTLP tracing without an injected test exporter requires an absolute endpoint;
- endpoint credentials, query data and fragments are rejected;
- batch size cannot exceed queue size;
- secret-bearing resource keys are rejected;
- configuration or dependency errors return `BLOCKED` with a bounded error type, not raw exception text.

## Runtime status

```text
NOT_CONFIGURED
NOT_PROBED
DEGRADED
BLOCKED
VERIFIED
```

A successful exporter return is not formal backend verification. `force_flush()` leaves the runtime at
`NOT_PROBED / export_accepted_unverified`. `VERIFIED` is reserved for a later live collector read or
trace-correlation certification. Queue loss, export failure or flush timeout produces `DEGRADED`.

## Bounded processor

`BoundedBatchSpanProcessor` is an application-owned non-blocking processor:

- sampled spans use `put_nowait`;
- a full queue increments an explicit drop counter;
- producers never wait for queue capacity;
- a daemon worker exports bounded batches;
- force-flush waits only for the configured timeout;
- shutdown returns after the configured timeout even if a non-compliant injected exporter remains hung;
- exporter exception messages are discarded;
- processor and exporter snapshots expose counts without payloads.

The OTLP exporter receives the configured network timeout. The implementation does not rely on the
Python SDK `BatchSpanProcessor.export_timeout_millis` argument.

## Domain spans

Required mapping:

```text
FORECAST_RUN        -> loto.forecast.run
RECEIVE             -> loto.api.request
DATA_LOAD           -> loto.data.load
DATA_VALIDATE       -> loto.data.validate
SPLIT_CREATE        -> loto.split.create
FEATURE_FIT         -> loto.feature.fit
FEATURE_TRANSFORM   -> loto.feature.transform
HPO_STUDY           -> loto.hpo.study
HPO_TRIAL           -> loto.hpo.trial
MODEL_LOAD          -> loto.model.load
FIT                 -> loto.model.fit
PREDICT             -> loto.model.predict
PREDICTION_LOCK     -> loto.prediction.lock
ACTUAL_READ         -> loto.actual.read
SCORE               -> loto.evaluation.score
ARTIFACT_PERSIST    -> loto.artifact.persist
REGISTRY_PERSIST    -> loto.registry.persist
PROMOTION_EVALUATE  -> loto.promotion.evaluate
```

Nested spans inherit the active trace. The active OpenTelemetry trace and span IDs are temporarily bound
to PR #141's context-variable telemetry context and restored on exit.

## Attribute policy

Span attributes are limited to 32 safe top-level values. Nested objects, unsupported values, NaN,
Infinity, sensitive keys and protected-actual keys are dropped. Strings are URI/token-redacted and
truncated to 256 characters.

Exception stack traces and messages are not recorded. Only bounded `error.type` is retained.

## FastAPI / ASGI

`instrument_fastapi_app()` installs `OpenTelemetryASGIMiddleware` once on an explicit application.

- it creates `SERVER` spans named `loto.api.request`;
- it extracts W3C propagation context;
- it binds an already-valid `X-Request-ID` to the telemetry context;
- it never generates or rewrites a request ID;
- it records method, scheme, server address/port and response status;
- it does not record request/response bodies, headers, query strings or raw URL paths.

PR #127 remains the owner of request-ID generation, validation and response headers. This PR does not
modify `src/loto/api/app.py`; final app wiring must occur after the stacked prerequisites are integrated.

## HTTPX

`TracedHTTPTransport` and `TracedAsyncHTTPTransport` wrap explicit transports.

- they create `CLIENT` spans;
- they inject W3C trace context;
- they record method, scheme, logical server and response status;
- they omit path, query, bodies and arbitrary headers;
- they preserve the wrapped transport and close semantics.

No existing HTTPX caller is changed in this PR.

## SQLAlchemy

`instrument_sqlalchemy_engine()` attaches listeners once to an explicit engine.

Recorded attributes:

```text
db.system.name
db.operation.name
```

SQL text, bind parameters, DSNs, hosts, database names and returned values are not retained. Engines can
be uninstrumented explicitly. No existing engine construction path is changed in this PR.

## Privacy deviation from generic HTTP semantic conventions

Generic HTTP conventions can include raw path or full URL attributes. This platform intentionally omits
those fields because path parameters and queries may contain run IDs, artifact identities, protected
actuals or credentials. Stable domain span names and bounded server/method/status attributes are used
instead. This is an explicit privacy tradeoff, not accidental omission.

## Rollback

Before merge, close the stacked Draft PR. After merge, revert normally. No dependency, lockfile,
database, data, workflow, deployment or historical-artifact migration exists.
