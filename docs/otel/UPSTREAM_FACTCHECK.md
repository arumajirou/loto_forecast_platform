# OpenTelemetry Upstream Fact Check

Fact-check date: `2026-08-06`

## Sources

Primary upstream references:

- OpenTelemetry Python trace exporter API and source;
- OpenTelemetry Python OTLP exporter API and source;
- OpenTelemetry HTTP semantic conventions;
- OpenTelemetry database client span conventions;
- OpenTelemetry semantic-conventions repository.

## Findings applied

### Queue and export timeout

The Python SDK exposes bounded queue and batch configuration on `BatchSpanProcessor`. Its current source
also states that the `export_timeout_millis` constructor argument is not used because the timeout cannot
be passed to `SpanExporter.export()` through that path.

Decision:

- do not claim that SDK batch-processor timeout enforces a deadline;
- use an application-owned non-blocking bounded queue;
- bound producer behavior with `put_nowait`;
- bound caller-side force-flush wait;
- pass the network deadline directly to the OTLP exporter;
- expose queue drops and export failures explicitly.

### OTLP exporter

The current Python gRPC and HTTP OTLP exporters accept an endpoint and backend request timeout. The HTTP
exporter sends traces to `/v1/traces`.

Decision:

- support `grpc` and `http/protobuf`;
- reject credentials embedded in endpoint URLs;
- append `/v1/traces` for HTTP when absent;
- use the configured exporter timeout;
- treat successful export as accepted but not formally verified.

### HTTP spans

Current HTTP conventions define `SERVER` and `CLIENT` span kinds and attributes including
`http.request.method`, `server.address`, `server.port`, `url.scheme` and response status. The generic
conventions can also include raw paths, routes, query strings or full URLs.

Decision:

- use correct `SERVER` and `CLIENT` kinds;
- retain bounded method/server/scheme/status fields;
- omit raw path, query, full URL, bodies and arbitrary headers under the platform privacy policy;
- record the privacy deviation explicitly.

### Database spans

Current database conventions use `db.system.name` and `db.operation.name`. Query text may be collected by
generic instrumentation, while parameter values are more restricted.

Decision:

- retain only system and operation names;
- never retain SQL text or parameters in this foundation;
- use a stable platform span name to avoid table/collection cardinality.

### Verification semantics

OpenTelemetry exporter success reports that an exporter accepted a batch. It does not prove that a
collector retained it, that Tempo indexed it, or that Grafana can retrieve it.

Decision:

- exporter success remains `NOT_PROBED / export_accepted_unverified`;
- `VERIFIED` is reserved for later live collector write/read and correlation evidence.

## Local compatibility probe

Executed environment:

```text
Python=3.13.5
opentelemetry-api=1.42.1
opentelemetry-sdk=1.42.1
opentelemetry-exporter-otlp=1.42.1
httpx=0.28.1
sqlalchemy=2.0.50
fastapi=0.128.2
starlette=0.50.0
```

The repository dependency ranges are broader and may resolve different versions. This local probe is not
a lockfile-resolution or complete repository compatibility claim.
