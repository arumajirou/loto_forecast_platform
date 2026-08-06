# Architecture

## 1. Logical layers

```text
[Forecast domain]
  data / features / models / evaluation / sealing / registry

[Evidence plane]
  configuration identity
  Data Access Ledger
  Runtime Certification
  artifact manifests
  prediction lock

[Telemetry plane]
  structured logs
  Prometheus metrics
  OpenTelemetry traces
  MLflow experiment records

[OSS interface plane]
  Grafana
  MLflow UI
  Optuna Dashboard
  Ray Dashboard
  Evidently

[Storage plane]
  immutable raw data
  Parquet
  DuckDB
  PostgreSQL
  artifact store
  Loki
  Tempo
  Prometheus
```

## 2. Dependency direction

Domain code may emit through telemetry interfaces. Telemetry adapters must not import model-specific
implementation modules. OSS SDKs are isolated behind adapters.

```text
domain -> telemetry protocol -> exporter adapter -> external service
```

External service SDKs must not become required imports for dependency-light core paths.

## 3. Signal ownership

| Signal | System of record |
|---|---|
| scientific run configuration | resolved config artifact |
| access chronology | Data Access Ledger |
| runtime proof | Runtime Certification evidence |
| operational time series | Prometheus |
| searchable application events | Loki |
| request and stage causality | Tempo |
| experiment comparison | MLflow |
| HPO state | Optuna/Ray storage |
| data quality snapshots | Evidently artifacts |
| immutable files | artifact store plus SHA-256 manifest |

## 4. Correlation model

The correlation chain is:

```text
request_id -> trace_id -> run_id -> protocol_hash -> artifact manifest
```

A Prometheus alert links to Grafana Explore. Logs contain `trace_id` and `run_id`. Traces contain `run.id`.
MLflow tags contain `run_id` and `protocol_hash`. No system replaces another source of truth.

## 5. Availability behavior

The forecasting pipeline shall not synchronously depend on Grafana. Required persistence backends may
fail closed according to configuration. Operational exporters use bounded asynchronous delivery and
explicit dropped-event counters.

## 6. OSS deployment

Grafana Alloy is the collector and routing layer. New Promtail-only deployment is not planned. Prometheus,
Loki and Tempo remain separate stores so retention and failure modes can be controlled independently.

## 7. UI policy

No new forecasting UI framework is introduced. Grafana is the operational home. MLflow is the experimental
home. Native HPO dashboards remain authoritative for their engines. The FastAPI root is a compatibility
portal, not a competing dashboard.
