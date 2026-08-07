# Implementation Plan

## Phase 0: Review and freeze

- review this documentation;
- confirm ownership boundaries with PR #121, #123, #124/#129 and #127;
- do not modify PR #79;
- restore actionable GitHub Actions tracked by issue #58;
- approve PR decomposition.

Exit gate: design approved, duplicate audit clean, CI can create workflow steps.

## Phase 1: Evaluation protocol completeness

PR: `fix/evaluation-protocol-completeness-v1`

- canonical metric registry;
- change default primary metric to Hit@±1;
- preserve legacy record identity;
- protocol v2;
- comparison budget identity;
- field-level protocol diff;
- seed mean/variance/worst aggregation;
- focused and regression tests.

No external dependency is required.

## Phase 2: Telemetry contract

PR: `feat/telemetry-contract-v1`

- strict event envelope;
- correlation context;
- redaction;
- metric registry and cardinality policy;
- no external exporter;
- fixture and property tests.

## Phase 3: OpenTelemetry instrumentation

PR: `feat/otel-instrumentation-v1`

- dependency update in isolated PR if required;
- FastAPI, HTTPX and SQLAlchemy instrumentation;
- domain manual spans;
- bounded batch processor;
- console/in-memory tests;
- OTLP smoke against a local collector.

## Phase 4: LGTM operations stack

PR: `ops/grafana-alloy-lgtm-v1`

- Alloy, Prometheus, Loki, Tempo and Grafana deployment assets;
- provisioned datasources and dashboards;
- retention and volume policy;
- authentication/network guidance;
- local smoke;
- restart and restore runbooks.

## Phase 5: Metrics expansion and host exporters

PRs:

- `feat/platform-metrics-v1`;
- `ops/host-exporters-v1`.

Implement pipeline, runtime, evaluation, data and artifact metrics. Add node_exporter. Probe dcgm-exporter;
use node_exporter textfile fallback if unsupported.

## Phase 6: MLflow live certification

PR: `feat/mlflow-live-certification-v1`

- real PostgreSQL-backed MLflow server;
- artifact storage;
- a bounded non-Holdout experiment;
- run tags, seed/fold artifacts and hashes;
- restart persistence;
- backup and restore drill;
- UI evidence.

## Phase 7: DataFrame contracts

PR: `feat/pandera-data-contracts-v1`

- dependency and lock update;
- four boundary schemas;
- adapters for pandas paths;
- fail-closed violations;
- no change to temporal provenance ownership.

## Phase 8: Evidently quality monitoring

PR: `feat/evidently-quality-monitoring-v1`

- immutable snapshot adapter;
- custom Hit@±1 metrics;
- data quality and drift report;
- delayed actual update;
- self-hosted UI only after report generation is verified.

## Phase 9: External evaluation adapter

PR: `feat/fev-evaluation-adapter-v1`

- pilot adapter;
- task fingerprint;
- skill score and win rate;
- explicit mapping to platform metric registry;
- no replacement of the platform acceptance gate.

## Phase 10: UI migration

PR: `refactor/api-dashboard-to-oss-portal-v1`

- preserve API endpoints;
- replace inline dashboard growth with links or redirect;
- do not remove compatibility page until Grafana and MLflow certification passes;
- update operator documentation.

## Phase 11: Optional lineage and profiling

- OpenLineage event pilot;
- Marquez only when required;
- Pyroscope only after operational stack is stable.

## Global gates

Each phase requires:

- duplicate audit;
- latest main base;
- focused tests;
- compileall;
- Ruff;
- mypy;
- relevant integration smoke;
- full pytest at final review;
- manifest and SHA-256;
- Draft PR;
- no merge without explicit human approval.
