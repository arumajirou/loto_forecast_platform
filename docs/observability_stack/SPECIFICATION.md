# LGTM Operations Stack v1 Specification

## Service inventory

| Service | Host interface | Internal responsibility |
|---|---|---|
| Grafana | `127.0.0.1:3000` | provisioned operational UI |
| Prometheus | `127.0.0.1:9090` | time-series storage, rule evaluation, remote-write receiver |
| Loki | `127.0.0.1:3100` | structured log storage and query |
| Tempo | `127.0.0.1:3200` | trace storage and query |
| Alloy | `127.0.0.1:12345` | collection, processing and routing |
| OTLP gRPC | `127.0.0.1:4317` | application trace/log ingress |
| OTLP HTTP | `127.0.0.1:4318` | application trace/log ingress |

## Signal routes

```text
/metrics -> Alloy prometheus.scrape -> prometheus.remote_write -> Prometheus
*.jsonl  -> Alloy loki.source.file -> loki.process -> Loki
OTLP logs -> Alloy receiver -> attributes/batch -> Loki
OTLP traces -> Alloy receiver -> batch/queue -> Tempo
```

Loki labels are limited to `component`, `level` and fixed `job`. Trace ID and Run ID remain searchable in
log content or structured metadata and are not index labels.

## Storage and retention

```text
Prometheus named volume: 15d and 20GB defaults
Loki named volume:       TSDB v13/filesystem, 168h
Tempo named volume:      local blocks/WAL, 168h
Grafana named volume:    users/settings/state
Alloy named volume:      component positions and local state
```

## Image identity

`images.versions.env` records exact reviewed tags. `resolve_image_digests.py` hashes the raw manifest returned
by `docker buildx imagetools inspect --raw`, then writes ignored lock files containing `repository@sha256`.
Formal startup requires those lock files. The lock JSON must be archived with certification evidence.

## Alerting boundary

Prometheus evaluates local rules for component down, telemetry drops, artifact integrity failure, prediction
lock verification failure and missing stage success. No Alertmanager or notification endpoint is configured;
alerts are visible in Prometheus/Grafana only. Notification routing requires a separate reviewed increment.

## Availability and failure behavior

- Forecast execution does not synchronously depend on this stack.
- Alloy queues are bounded and retry for finite periods.
- Missing image identity or secrets blocks startup.
- Backend unavailability is detected by smoke checks and Prometheus targets.
- Backup stops services to obtain a consistent local volume snapshot.
- Restore is destructive, checksum-gated and never auto-starts.
