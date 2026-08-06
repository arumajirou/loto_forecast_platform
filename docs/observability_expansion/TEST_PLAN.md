# Test and Verification Plan

## 1. Test levels

### Static

- Python AST and compileall;
- Ruff format and lint;
- mypy;
- JSON/YAML/TOML parse;
- dashboard JSON validation;
- container configuration validation;
- secret-pattern scan;
- dependency and license inventory;
- SHA-256 manifest verification.

### Unit

- strict event contract;
- redaction;
- correlation context isolation;
- protocol canonicalization;
- protocol diff;
- metric alias mapping;
- worst-seed direction;
- Prometheus cardinality allowlist;
- Pandera schemas;
- Evidently custom metrics.

### Integration

- FastAPI request creates request ID and trace;
- nested pipeline spans share the trace;
- JSON log includes trace and run identity;
- Prometheus scrape contains approved metrics;
- Alloy routes logs and traces;
- Grafana datasources are healthy;
- MLflow persists a bounded experiment;
- Optuna Dashboard reads a persisted study;
- Evidently reads immutable snapshots.

### Failure injection

- Loki unavailable;
- Tempo unavailable;
- Prometheus unavailable;
- OTLP timeout;
- exporter queue full;
- MLflow unavailable;
- PostgreSQL restart;
- artifact store write failure;
- malformed telemetry event;
- secret in exception;
- invalid protocol comparison;
- non-finite prediction;
- CPU fallback in CUDA-required run.

## 2. Evaluation acceptance

Required test scenarios:

- Hit@±1 is the default primary metric;
- all requested secondary metrics are present;
- Random/fixed/mean/median/last/frequency/statistical baselines are represented;
- Train-only preprocessing and tuning evidence remains valid;
- all seeds are retained;
- mean, population variance and worst value match independent calculations;
- a result with better MAE but worse Hit@±1 is not selected when Hit@±1 is primary;
- protocol changes in alpha, correction, conformal policy or baseline inventory change the hash;
- protocol diff identifies the exact change;
- legacy protocol records remain readable but are not silently comparable.

## 3. Telemetry acceptance

- no prohibited value is a Prometheus label;
- metric series count remains below an approved bound in stress fixtures;
- logs and traces redact secrets;
- protected actuals are absent before reveal;
- telemetry timeout does not hang the pipeline;
- required audit evidence failure blocks formal promotion;
- optional exporter failure produces a degraded status;
- logs, traces and MLflow records correlate to one Run ID.

## 4. Live certification

Formal service certification requires:

```text
service version/digest
configuration hash
start timestamp
process/container identity
health evidence
write/read evidence
restart evidence
retention evidence
backup/restore evidence where persistent
logs
metrics
trace or request correlation
```

A UI screenshot alone is not sufficient.

## 5. Performance

Measure:

- logging overhead;
- span overhead;
- metric update overhead;
- exporter queue memory;
- forecast latency with telemetry enabled/disabled;
- dropped telemetry under load;
- Grafana query latency;
- Loki and Tempo retention size;
- MLflow artifact upload duration.

Define budgets before production-candidate certification.

## 6. Final commands

During implementation, run focused tests first. At final review:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run python -m compileall -q src tests
uv run pytest -q
```

Additional service-specific smoke commands belong in each PR runbook.
