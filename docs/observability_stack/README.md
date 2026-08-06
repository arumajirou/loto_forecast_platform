# Local Grafana Alloy LGTM Stack v1

## Status

```text
LOCAL_SINGLE_NODE_EVALUATION_PROFILE
STACKED_ON_PR_154
STATIC_VALIDATION_ONLY_IN_CURRENT_ENVIRONMENT
LIVE_CERTIFICATION_REQUIRED_BEFORE_PRODUCTION
```

## Purpose

This deployment provides a local, operator-controlled evidence interface:

```text
application /metrics -> Alloy scrape -> Prometheus remote-write receiver
structured JSONL      -> Alloy file source -> Loki
OTLP traces/logs      -> Alloy receiver -> Tempo / Loki
Prometheus/Loki/Tempo -> Grafana provisioned datasources and dashboard
```

It is not a high-availability or internet-facing production topology. Prometheus, Loki and Tempo remain
separate stores, and Grafana is the operational UI. The deployment does not replace immutable artifacts,
Data Access Ledger, Runtime Certification, prediction locks or MLflow.

## Reviewed image tags

```text
grafana/grafana:13.1.1
grafana/alloy:v1.18.0
prom/prometheus:v3.11.3
grafana/loki:3.7.2
grafana/tempo:2.10.5
busybox:1.37.0-uclibc
```

Tags are review inputs, not formal runtime identity. Before startup, resolve them to immutable manifest
digests:

```bash
python scripts/observability/resolve_image_digests.py
python scripts/observability/validate_stack.py --require-lock
```

The generated lock files are intentionally ignored by Git. Archive them with each live certification
record instead of silently changing the committed deployment source.

## First start

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail

cp -n deploy/observability/.env.example deploy/observability/.env
install -m 0600 /dev/null deploy/observability/secrets/grafana_admin_user
install -m 0600 /dev/null deploy/observability/secrets/grafana_admin_password
printf '%s' 'admin' > deploy/observability/secrets/grafana_admin_user
read -r -s -p 'Grafana admin password: ' GRAFANA_PASSWORD
echo
printf '%s' "$GRAFANA_PASSWORD" > deploy/observability/secrets/grafana_admin_password
unset GRAFANA_PASSWORD

python scripts/observability/resolve_image_digests.py
bash scripts/observability/start.sh
```

Local interfaces:

```text
Grafana     http://127.0.0.1:3000
Prometheus  http://127.0.0.1:9090
Loki        http://127.0.0.1:3100
Tempo       http://127.0.0.1:3200
Alloy       http://127.0.0.1:12345
OTLP gRPC   127.0.0.1:4317
OTLP HTTP   127.0.0.1:4318
```

Every published port is loopback-only. The deployment does not mount the Docker socket. Grafana anonymous
access and sign-up are disabled. No public ingress, TLS terminator or identity proxy is included.

## Application integration boundary

The default Alloy scrape target is:

```text
host.docker.internal:8000
```

Set `LOTO_METRICS_TARGET` to the actual application host and port. PR #154 deliberately did not modify the
existing FastAPI `/metrics` registry, so a live platform-metric scrape remains an integration gate.

Configure PR #147's OTLP endpoint to the host listener only after the application tracing integration is
approved:

```text
otlp_protocol=grpc
otlp_endpoint=http://127.0.0.1:4317
```

## Retention and volumes

```text
Prometheus: 15d and 20GB defaults
Loki:       168h
Tempo:      168h
```

Named volumes persist Grafana, Prometheus, Loki, Tempo and Alloy state. Filesystem Loki/Tempo backends are
acceptable only for this local single-node profile. Object storage, replication and HA require a separate
production design and certification.

## Backup and restore

```bash
bash scripts/observability/backup_restore.sh backup
CONFIRM_RESTORE=YES bash scripts/observability/backup_restore.sh restore \
  deploy/observability/backups/<timestamp>
```

Backup stops services before archiving volumes. Restore verifies `SHA256SUMS`, requires explicit destructive
confirmation and does not restart services automatically.

## Required live certification

A successful `docker compose up` is insufficient. Formal evidence must include:

- resolved image digests and configuration SHA-256;
- `docker compose config` output;
- component readiness and process identity;
- Prometheus target health and real application samples;
- JSON log write/read in Loki;
- OTLP trace write/read in Tempo;
- Grafana datasource health and dashboard query evidence;
- restart persistence;
- backup and restore drill;
- retention evidence;
- resource and disk usage;
- vulnerability scan results;
- proof that all host listeners remain loopback-only.

## Non-claims

This increment does not claim production readiness, authentication beyond local Grafana credentials,
TLS, HA, remote object storage, live application metrics, retained traces, retained logs, alerting, or
backup/restore execution.
