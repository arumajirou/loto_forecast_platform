# LGTM Operations Stack v1 Architecture

## Context

```text
Forecast domain
  -> exporter-neutral telemetry contract (PR #141)
  -> OpenTelemetry adapters (PR #147)
  -> bounded Prometheus collectors (PR #154)
  -> Alloy routing
  -> Prometheus / Loki / Tempo
  -> Grafana
```

The stack is downstream of domain and evidence-plane systems. It does not become the source of truth for
scientific configuration, data access chronology, runtime certification, prediction locks or immutable
artifacts.

## Deployment topology

All five services run on one user-controlled Docker host. Only loopback listeners are published. Container
DNS is used internally. The application remains outside the Compose project and is reached through the
explicit `LOTO_METRICS_TARGET`; no Docker socket discovery is permitted.

## Trust boundaries

- Grafana is the only intended human UI.
- Prometheus, Loki, Tempo and Alloy have no public ingress.
- Grafana credentials are local files, not Compose values.
- Loki and Tempo have no built-in authentication in this profile and must remain loopback/internal only.
- Image tags are not runtime identity; resolved digests are mandatory.

## Production delta

A production topology would require TLS, identity-aware ingress, remote object storage, backup automation,
replication/HA, resource limits, capacity planning, vulnerability scanning, retention/legal review and live
service certification. None is inferred from this local profile.
