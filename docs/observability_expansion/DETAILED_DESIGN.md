# Detailed Design

## 1. Package layout

Proposed modules:

```text
src/loto/telemetry/
  __init__.py
  contracts.py
  context.py
  logging.py
  metrics.py
  tracing.py
  redaction.py
  exporters.py

src/loto/evaluation/
  metric_registry.py
  protocol_v2.py
  protocol_diff.py
  seed_summary.py

src/loto/data_contracts/
  raw.py
  normalized.py
  split.py
  prediction.py
  metrics.py

src/loto/quality/
  evidently_adapter.py

src/loto/external_evaluation/
  fev_adapter.py
```

Deployment assets:

```text
deploy/observability/
  compose.yaml
  alloy/
  prometheus/
  loki/
  tempo/
  grafana/
    provisioning/
    dashboards/
  alerting/
```

## 2. Telemetry models

### 2.1 Strict event contract

Use Pydantic v2:

```python
ConfigDict(
    extra="forbid",
    strict=True,
    allow_inf_nan=False,
    validate_assignment=True,
)
```

Required bounded enums:

```text
Severity
Component
Stage
EventStatus
ErrorCode
DeviceKind
SplitKind
```

`attributes` shall have configurable maximum keys, maximum serialized bytes and value-type restrictions.

### 2.2 Correlation context

Use context variables for:

```text
request_id
run_id
trace_id
span_id
game_id
model_id
fold_id
seed
```

Request ID and trace ID are correlated but not treated as interchangeable. PR #127 remains the source of
HTTP request ID behavior.

### 2.3 Redaction

Redaction shall detect key names and URI patterns:

```text
password
passwd
secret
token
authorization
api_key
dsn
database_url
smtp
cookie
```

Redaction occurs before formatting and before exporter queues.

## 3. OpenTelemetry

### 3.1 Configuration

Configuration fields:

```text
enabled
service_name
service_version
environment
otlp_endpoint
otlp_protocol
export_timeout_seconds
batch_queue_size
batch_size
sample_ratio
resource_attributes
instrument_fastapi
instrument_httpx
instrument_sqlalchemy
```

Default is disabled unless explicitly configured. Missing exporter configuration shall not fabricate
success.

### 3.2 Manual instrumentation

Automatic instrumentation covers transport boundaries. Manual spans cover domain boundaries such as fit,
predict, lock and score.

Exceptions shall be recorded with a sanitized type and bounded message. Protected data shall not be span
attributes.

## 4. Metrics registry

A central registry factory shall avoid accidental duplicate registrations. Tests shall construct isolated
CollectorRegistry instances. The application export path shall explicitly combine approved collectors.

Histograms shall define reviewed buckets. Durations shall use seconds. Timestamps shall use Unix seconds.

## 5. Evaluation protocol v2

### 5.1 Canonical payload

```text
schema_version
game_geometry
data_snapshot
split_manifest
feature_manifest
metric_manifest
baseline_manifest
statistical_policy
calibration_policy
sentinel_policy
postprocess_policy
seed_policy
search_policy
resource_budget
software_identity
```

The v1 hash remains readable. v2 comparisons to v1 are invalid unless an explicit migration adapter proves
equivalence.

### 5.2 Primary metric migration

The standard configuration shall use `hit_at_1`. Existing historical outputs keep their original value and
are tagged `LEGACY_PRIMARY_POSITION_MAE` where applicable. Historical records shall not be rewritten.

### 5.3 Protocol diff

Diff output:

```json
{
  "comparable": false,
  "left_hash": "...",
  "right_hash": "...",
  "differences": [
    {
      "path": "statistical_policy.alpha",
      "left": 0.05,
      "right": 0.01,
      "severity": "RESULT_AFFECTING"
    }
  ]
}
```

## 6. Pandera boundaries

Schemas shall validate:

- exact required columns;
- data type;
- nullable policy;
- range;
- uniqueness;
- monotonic chronology;
- no duplicate draw identity;
- legal position values;
- finite predictions and metrics;
- actual presence policy.

Do not duplicate the Feature Availability Registry or Data Access Ledger. Pandera validates table shape and
values; the other systems validate temporal provenance and access chronology.

## 7. Grafana dashboards

Dashboards are JSON committed to the repository and provisioned by file. Each panel includes:

```text
owner
purpose
data source
query
unit
threshold rationale
runbook link
```

Alerts must have a runbook and bounded labels. Initial alerts:

- required dependency unready;
- no successful data acquisition within expected interval;
- prediction lock verification failure;
- artifact integrity failure;
- non-finite output;
- CPU fallback during CUDA-required run;
- Prospective actual overdue;
- registry persistence failure;
- disk space low;
- exporter queue drops.

## 8. MLflow

Run naming:

```text
<game>/<model_id>/<run_id>
```

Nested runs may represent seeds and folds only when the query burden is acceptable. Otherwise fold and seed
tables remain artifacts with aggregate metrics on the parent.

No actual value is logged before the authorized reveal event.

## 9. Evidently

The adapter reads immutable metric and feature snapshots. It shall not modify training data. Custom metrics
shall implement Hit@±1 and all-position Hit@±1.

Reports are versioned and stored as artifacts. Monitoring UI deployment is a separate operations gate.

## 10. Security

- no public unauthenticated Grafana, MLflow, Ray or Optuna service;
- bind local development services to loopback by default;
- secrets from environment or secret store, never repository files;
- sanitize logs and traces;
- restrict dashboard links to configured allowlisted origins;
- preserve audit event immutability.
