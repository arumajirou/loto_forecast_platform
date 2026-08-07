# FastAPI Health and Dependency Observability Contract

## Status

`FOUNDATION_V1 / BACKWARD_COMPATIBLE / NO_LIVE_BACKEND_ASSERTIONS`

## Existing compatibility endpoint

`GET /health` is unchanged. It continues to return HTTP 200 and the existing fields:

```json
{
  "status": "ok",
  "output_dir": "<configured output path>",
  "auth_enabled": false
}
```

The request-ID middleware adds an `X-Request-ID` response header, but does not add a field to the
legacy JSON body.

## Request identity

Every HTTP response receives `X-Request-ID`.

- a caller-supplied value is retained only when it matches `[A-Za-z0-9._:-]{1,128}`;
- otherwise a random 32-character hexadecimal ID is generated;
- request IDs are never used as Prometheus labels;
- the three new health responses also include `request_id` in their JSON body.

## Endpoints

### `GET /livez`

Purpose: process liveness only.

- does not run dependency probes;
- returns HTTP 200 while the ASGI process can serve the request;
- optional or required dependency failures do not change liveness.

Example:

```json
{
  "status": "ALIVE",
  "request_id": "trace-123"
}
```

### `GET /readyz`

Purpose: admission and traffic-routing readiness.

- runs all dependency probes concurrently;
- applies a bounded per-probe timeout;
- returns HTTP 503 when a required dependency makes the application `UNREADY`;
- returns HTTP 200 for both `READY` and `DEGRADED`;
- optional dependency failure can produce `DEGRADED`, but never makes the process dead.

### `GET /health/dependencies`

Purpose: diagnostic dependency snapshot.

- executes the same probe set and readiness policy as `/readyz`;
- always returns HTTP 200 so operators can inspect an `UNREADY` snapshot;
- does not expose DSNs, credentials, exception strings, source URLs, or arbitrary probe metadata.

## Dependency inventory

The inventory is fixed and complete:

```text
registry_database
postgresql
mlflow
artifact_store
prediction_lock_verifier
data_freshness
gpu_service
job_queue
```

The default criticality policy is:

| Dependency | Criticality |
|---|---|
| registry database | REQUIRED |
| artifact store | REQUIRED |
| PostgreSQL | OPTIONAL |
| MLflow | OPTIONAL |
| prediction lock verifier | OPTIONAL |
| data freshness | OPTIONAL |
| GPU service | OPTIONAL |
| job queue | OPTIONAL |

The application accepts an injected complete `DependencyProbeSpec` inventory. A later deployment PR
may change criticality explicitly after documenting which routes depend on each service.

## Dependency states

| State | Meaning |
|---|---|
| `CONFIGURED_AND_READY` | Configured and the injected probe completed successfully. |
| `CONFIGURED_BUT_UNAVAILABLE` | Configured, but the probe reported unavailable, timed out, or raised. |
| `NOT_CONFIGURED` | Explicitly not configured. No probe is run. |
| `NOT_APPLICABLE` | Not applicable to this deployment. No probe is run. |
| `UNKNOWN` | Configuration or readiness cannot be established safely. |

Default probes make no backend connection. The two default required dependencies are represented as
configured with no registered probe, therefore `UNKNOWN`. Optional dependencies default to
`NOT_CONFIGURED`. Consequently, the default `/readyz` result is intentionally fail-closed rather than
a fabricated ready result.

## Overall readiness

Required dependency policy:

- `CONFIGURED_AND_READY`: healthy;
- `NOT_APPLICABLE`: neutral;
- `CONFIGURED_BUT_UNAVAILABLE`, `NOT_CONFIGURED`, or `UNKNOWN`: `UNREADY`.

Optional dependency policy:

- `CONFIGURED_AND_READY`, `NOT_CONFIGURED`, or `NOT_APPLICABLE`: neutral;
- `CONFIGURED_BUT_UNAVAILABLE` or `UNKNOWN`: `DEGRADED`.

## Structured response

```json
{
  "status": "DEGRADED",
  "request_id": "trace-123",
  "checked_at_utc": "2026-08-06T06:00:00Z",
  "probe_timeout_seconds": 1.0,
  "dependencies": [
    {
      "dependency": "mlflow",
      "criticality": "OPTIONAL",
      "state": "CONFIGURED_BUT_UNAVAILABLE",
      "ready": false,
      "detail_code": "probe_timeout",
      "latency_ms": 1000.0,
      "checked_at_utc": "2026-08-06T06:00:00Z"
    }
  ]
}
```

`detail_code` is a bounded machine code. Raw exception messages are never included.

## Probe interface

A probe implements:

```python
class DependencyProbe(Protocol):
    async def probe(self) -> ProbeObservation: ...
```

The service injects identity, criticality, configuration state, timeout handling, timing,
classification, and metrics. Provider-specific probes return only a strict `ProbeObservation`.

No live PostgreSQL, MLflow, object-store, GPU, queue, or official-data probe is included in this PR.
