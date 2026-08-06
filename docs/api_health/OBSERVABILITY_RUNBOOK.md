# Health and Dependency Observability Runbook

## Endpoint use

- Kubernetes or equivalent liveness check: `GET /livez`.
- Traffic admission/readiness check: `GET /readyz`.
- Operator diagnosis: `GET /health/dependencies`.
- Legacy dashboard compatibility: `GET /health`.
- Metrics scraping: `GET /metrics`.

Do not use `/health` as a readiness gate. It intentionally preserves the historical lightweight
contract.

## Response interpretation

### `READY`

Every required dependency is `CONFIGURED_AND_READY` or `NOT_APPLICABLE`. Optional dependencies are
not currently degraded.

### `DEGRADED`

Required dependencies remain acceptable, but at least one optional configured dependency is
unavailable or unknown. Keep the process running and route traffic only if the affected optional
capability is not needed for the request class.

### `UNREADY`

At least one required dependency is unavailable, unknown, or not configured. Stop new traffic through
the readiness gate, but do not restart the process solely because `/readyz` is 503. `/livez` remains
the restart signal.

## Default foundation behavior

The default installation performs no backend calls and therefore does not claim success:

- `registry_database`: `UNKNOWN`, required;
- `artifact_store`: `UNKNOWN`, required;
- all other dependencies: `NOT_CONFIGURED`, optional.

The resulting default `/readyz` is HTTP 503. A deployment must inject real bounded probes before using
this endpoint as a production readiness gate.

## Probe implementation checklist

For each later dependency-specific PR:

1. keep the probe read-only and bounded;
2. use the common timeout instead of an unbounded client call;
3. return only `CONFIGURED_AND_READY` or `CONFIGURED_BUT_UNAVAILABLE`;
4. never return credentials, DSNs, tokens, bucket URLs, query text, or exception strings;
5. avoid creating schemas, files, runs, jobs, experiments, or GPU workloads;
6. add fake-client tests for success, failure, timeout, and malformed responses;
7. test that `/livez` is unaffected;
8. document whether the dependency is required or optional;
9. run a real target-environment probe separately and label that evidence accurately;
10. do not infer accuracy, prediction-lock validity, or data freshness from process connectivity.

## Prometheus metrics

The implementation exports:

```text
loto_health_endpoint_requests_total{endpoint,outcome}
loto_dependency_probe_total{dependency,state}
loto_dependency_ready{dependency}
loto_dependency_probe_duration_seconds{dependency}
loto_api_readiness_status{status}
```

Allowed label values are bounded enums or the fixed eight-dependency inventory. Never add request ID,
run ID, model ID, error message, DSN, host, path, source URL, job ID, PID, or user ID as a label.

Suggested alerts:

- `loto_api_readiness_status{status="UNREADY"} == 1` sustained for the deployment's grace period;
- required `loto_dependency_ready == 0` after a configured real probe is installed;
- increase in `loto_dependency_probe_total{state="CONFIGURED_BUT_UNAVAILABLE"}`;
- probe duration approaching the configured timeout.

## Secret handling

Health responses expose only dependency name, criticality, state, a bounded detail code, latency, and
timestamp. Probe exceptions are converted to `probe_exception`; timeout is `probe_timeout`.

When debugging, inspect secrets only in the owning secret manager or deployment configuration. Do not
add raw client exceptions to health responses or Prometheus labels.

## Request IDs

Use the returned `X-Request-ID` to correlate reverse-proxy and application logs. The current
foundation does not add request IDs to metrics labels and does not persist them itself.

## Rollback

The change is limited to one new health module, focused tests/docs, and a small additive integration in
`create_app`. Rollback by reverting the PR. The legacy `/health` body and `/metrics` route require no
data migration.
