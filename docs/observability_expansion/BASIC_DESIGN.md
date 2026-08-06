# Basic Design

## 1. Design principles

1. Scientific evaluation and operational observability are separate but correlated.
2. OSS interfaces are adopted by responsibility; a monolithic custom UI is prohibited.
3. High-cardinality identity belongs in logs, traces and experiment tracking, not metrics labels.
4. Every formal result is bound to configuration, data, code, protocol and model identities.
5. Live connectivity is never inferred from installed packages or configured URLs.
6. Telemetry must not leak protected actuals or secrets.
7. Holdout and Prospective remain governed by existing approval and sealing mechanisms.
8. Existing PR ownership is preserved.

## 2. Target architecture

```text
FastAPI / CLI / Orchestrator / Workers
        │
        ├── structured JSON events
        ├── OpenTelemetry traces
        ├── Prometheus metrics
        └── MLflow run records
                │
        Grafana Alloy / direct bounded clients
        ├── Loki
        ├── Tempo
        └── Prometheus
                │
             Grafana

Evaluation artifacts ──> PostgreSQL / Artifact Store / MLflow UI
Optuna studies ────────> Optuna Dashboard
Ray workloads ────────> Ray Dashboard
Quality snapshots ────> Evidently
```

## 3. Responsibility boundaries

| Component | Owner |
|---|---|
| `/livez`, `/readyz`, dependency inventory, request ID | PR #127 |
| data access chronology | PR #124/#129 |
| runtime execution evidence | PR #123 |
| strict resolved configuration | PR #121 |
| telemetry envelope and semantic conventions | new telemetry contract PR |
| OpenTelemetry instrumentation | new OTel PR |
| Grafana stack assets | new operations PR |
| evaluation protocol completeness | new evaluation PR |
| MLflow live certification | new live integration PR |
| DataFrame contracts | new Pandera PR |
| data quality and drift UI | new Evidently PR |

## 4. Migration strategy

The existing FastAPI dashboard remains available during migration. It shall not gain major new features.
After Grafana and MLflow are certified, the root page becomes a small portal or redirect.

The existing `/metrics` endpoint remains compatible. Metric registration shall be centralized so KPI Lab,
API readiness and pipeline metrics are all exported intentionally.

## 5. Deployment profiles

### Developer profile

- local file artifacts;
- optional local Prometheus/Grafana;
- console JSON logs;
- in-memory or local OTLP collector;
- SQLite where currently supported.

### Integration profile

- PostgreSQL;
- MLflow server;
- Prometheus;
- Alloy;
- Loki;
- Tempo;
- Grafana;
- optional Evidently service.

### Production-candidate profile

- immutable deployment config;
- persistent volumes and backup policy;
- authentication and network restrictions;
- live readiness probes;
- alert routing;
- restore drill evidence;
- no automatic promotion without formal approval.
