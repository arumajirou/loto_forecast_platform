# OSS Selection and Adoption Policy

## 1. Adopt now

| OSS | Decision | Responsibility |
|---|---|---|
| Prometheus | KEEP_AND_EXPAND | operational metrics and alert inputs |
| Grafana | ADOPT | dashboards, Explore and alerts |
| Grafana Alloy | ADOPT | collection, processing and export |
| Loki | ADOPT | structured log storage and search |
| Tempo | ADOPT | OpenTelemetry trace storage |
| OpenTelemetry Python | ADOPT | tracing and semantic instrumentation |
| MLflow | ACTIVATE_AND_CERTIFY | experiment tracking, artifacts and registry UI |
| Optuna Dashboard | ACTIVATE | Optuna study visualization |
| Ray Dashboard | ACTIVATE_WHEN_RAY | Ray-native operations |
| Pandera | ADOPT_INCREMENTALLY | DataFrame boundary contracts |
| Evidently | ADOPT_INCREMENTALLY | quality, drift and delayed performance |
| node_exporter | ADOPT | host metrics |

## 2. Conditional

| OSS | Decision | Condition |
|---|---|---|
| NVIDIA dcgm-exporter | TARGET_HOST_PROBE | consumer GPU/driver support must be verified |
| fev | ADAPTER_PILOT | retain platform primary metrics and legal outcome rules |
| OpenLineage | EVENT_ONLY_PILOT | add after core telemetry stabilizes |
| Marquez | OPTIONAL | only when lineage UI has an operator use case |
| Pyroscope | OPTIONAL | after trace and metric stack is stable |
| Great Expectations | OPTIONAL | only for Data Docs needs |

## 3. Do not add now

| OSS / approach | Reason |
|---|---|
| custom React SPA | duplicates Grafana, MLflow and native dashboards |
| Streamlit operational dashboard | becomes another stateful UI and security surface |
| Aim | overlaps MLflow |
| Deepchecks | overlaps current evaluation and Evidently plan |
| whylogs | overlaps Pandera/Evidently for current scope |
| DataHub | excessive operational weight for current scale |
| OpenMetadata | excessive operational weight for current scale |
| new Promtail-only stack | Alloy is preferred collector path |

## 4. Versioning

Exact versions shall be resolved in each dependency or deployment PR from official release information.
This design document intentionally does not fabricate future-compatible pins. Every adopted component shall
have:

- official repository and license;
- immutable container digest or package lock;
- vulnerability scan;
- configuration schema;
- backup/restore policy where persistent;
- upgrade and rollback runbook.
