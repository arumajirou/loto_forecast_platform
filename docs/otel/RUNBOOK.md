# OpenTelemetry Instrumentation v1 Runbook

## Preconditions

```text
PR #141 telemetry contract available
repository full extra installed
immutable service version known
collector endpoint separately approved
```

## Construct runtime

```python
from loto.telemetry.otel import OtlpProtocol, TracingConfig, configure_tracing

config = TracingConfig(
    enabled=True,
    service_name="loto-forecast-platform",
    service_version="3.2.0",
    environment="development",
    otlp_endpoint="http://127.0.0.1:4318",
    otlp_protocol=OtlpProtocol.HTTP_PROTOBUF,
    export_timeout_seconds=5.0,
    batch_queue_size=2048,
    batch_size=512,
)
runtime = configure_tracing(config)
```

Stop when:

```text
status=BLOCKED
reason=service_version_unpinned
reason=otlp_endpoint_missing
reason starts with configuration_error:
```

`NOT_PROBED` is expected immediately after configuration. It is not a readiness claim.

## FastAPI helper

```python
from loto.telemetry.otel import instrument_fastapi_app

instrument_fastapi_app(app, runtime)
```

Do not add another request-ID generator. PR #127 remains authoritative for that behavior.

## Domain span

```python
from loto.telemetry import Stage
from loto.telemetry.otel import domain_span

with domain_span(runtime, Stage.PREDICT, attributes={"horizon": 1}):
    prediction = provider.predict(request)
```

Never add Actual values, targets, secrets, raw paths, SQL or free-form exception strings as span
attributes.

## HTTPX

```python
import httpx
from loto.telemetry.otel import TracedHTTPTransport

with httpx.Client(transport=TracedHTTPTransport(runtime)) as client:
    response = client.get("https://approved-service.example/status")
```

## SQLAlchemy

```python
from loto.telemetry.otel import instrument_sqlalchemy_engine

instrument_sqlalchemy_engine(engine, runtime)
```

## Flush and inspect

```python
runtime = runtime.force_flush()
print(runtime.status, runtime.reason)
print(runtime.processor_snapshot())
print(runtime.exporter_snapshot())
```

Interpretation:

```text
NOT_PROBED / export_accepted_unverified = exporter accepted data; backend not certified
DEGRADED / export_degraded = queue drop, timeout or export failure
BLOCKED = invalid or unavailable configuration
```

Do not promote `NOT_PROBED` to `VERIFIED` without retained live collector and query evidence.

## Shutdown

```python
runtime.shutdown()
```

Shutdown is bounded by `export_timeout_seconds`. Required audit evidence remains governed by the PR #141
contract and caller gate; traces in this increment are operational evidence and do not replace immutable
audit artifacts.
