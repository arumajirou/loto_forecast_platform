# Functional Specification

## 1. Evaluation service

### 1.1 Canonical metric registry

The implementation shall expose a central registry with:

```text
metric_id
display_name
direction
scope
aggregation
required_for_point
required_for_probabilistic
legacy_aliases
```

Canonical IDs:

```text
hit_at_1
position_hit_at_1
all_positions_hit_at_1
mae
mse
rmse
brier
ece
log_loss
crps
energy_score
coverage
interval_width
```

### 1.2 Protocol projection

The protocol builder shall project resolved configuration and runtime declarations into a canonical
payload. Operational values that do not change scientific interpretation may be excluded only by an
explicit allowlist.

Outputs:

- `protocol.json`;
- `protocol_hash.txt`;
- `protocol_diff.json`;
- `comparison_budget.json`;
- `comparison_budget_hash.txt`.

### 1.3 Seed aggregation

For every metric:

```text
count
mean
population_variance
standard_deviation
minimum
maximum
worst_value
worst_seed
```

Worst direction is determined by the metric registry.

### 1.4 Baseline comparison

Every formal evaluation shall include Random, fixed value, mean, median, last value, frequency and
approved statistical baselines when applicable. Missing required baselines produce `INCOMPLETE`.

## 2. Telemetry contract

### 2.1 Event envelope

```json
{
  "schema_version": "1.0",
  "timestamp_utc": "2026-08-06T00:00:00Z",
  "severity": "INFO",
  "event_name": "model.predict.completed",
  "component": "forecast_worker",
  "status": "PASS",
  "run_id": "run-...",
  "request_id": null,
  "trace_id": "...",
  "span_id": "...",
  "game_id": "numbers4",
  "model_id": "nf-auto-tft",
  "model_revision": "revision-or-UNPINNED",
  "stage": "PREDICT",
  "fold_id": 2,
  "seed": 1,
  "duration_ms": 123.4,
  "error_code": null
}
```

Free-form payloads shall be nested under a size-bounded `attributes` field and redacted.

### 2.2 Trace spans

Required span names:

```text
loto.api.request
loto.forecast.run
loto.data.load
loto.data.validate
loto.split.create
loto.feature.fit
loto.feature.transform
loto.hpo.study
loto.hpo.trial
loto.model.load
loto.model.fit
loto.model.predict
loto.prediction.lock
loto.actual.read
loto.evaluation.score
loto.artifact.persist
loto.registry.persist
loto.promotion.evaluate
```

Span status shall use OpenTelemetry status plus a bounded platform status attribute.

### 2.3 Prometheus metrics

Core families:

```text
loto_pipeline_runs_total{stage,status}
loto_pipeline_stage_duration_seconds{stage,status}
loto_pipeline_active_runs{stage}
loto_pipeline_last_success_timestamp_seconds{stage}

loto_model_inference_total{provider,status,device}
loto_model_inference_duration_seconds{provider,device,horizon}
loto_model_load_duration_seconds{provider,device}
loto_model_cpu_fallback_total{provider}
loto_model_output_nonfinite_total{provider}
loto_model_replay_mismatch_total{provider}

loto_evaluation_runs_total{game,status}
loto_evaluation_hit_at_1{game,position,split}
loto_evaluation_all_positions_hit_at_1{game,split}
loto_evaluation_mae{game,position,split}
loto_evaluation_worst_seed_hit_at_1{game,split}
loto_evaluation_protocol_mismatch_total{game}
loto_evaluation_leakage_sentinel_total{game,result}

loto_data_rows{game,role}
loto_data_last_observation_timestamp_seconds{game}
loto_data_missing_values{game,column_group}
loto_data_duplicate_rows{game}
loto_data_order_violations_total{game}
loto_data_future_access_blocked_total{stage}

loto_registry_operations_total{operation,status}
loto_artifact_integrity_failure_total{artifact_type}
loto_prediction_lock_verification_total{status}
```

### 2.4 Cardinality constraints

Prohibited labels:

```text
run_id
request_id
trace_id
span_id
git_sha
model_revision
artifact_path
dataset_hash
config_hash
error_message
user_id
```

These values belong in logs, traces or MLflow tags.

## 3. OSS UI integration

### 3.1 Grafana

Provision dashboards as code. No dashboard may depend on undocumented metric names.

Required dashboards:

- Platform Overview;
- API and Dependency Health;
- Data Freshness and Quality;
- Training and HPO;
- Runtime Certification;
- GPU and Host Resources;
- Evaluation and Baselines;
- Prospective Lifecycle;
- Registry and Promotion;
- CI and Release Status.

### 3.2 MLflow

Each run shall log:

- config, data, code and protocol hashes;
- git commit;
- model ID and immutable revision;
- all seeds and fold metrics;
- mean, variance and worst values;
- predictions and actuals according to reveal policy;
- runtime evidence URI;
- artifact manifest URI;
- tags for game, split and formal status.

### 3.3 Evidently

Initial reports:

- normalized-data quality;
- feature distribution drift;
- prediction distribution;
- delayed actual performance;
- position-level Hit@±1 and MAE;
- baseline delta;
- freshness.

## 4. Error behavior

- Exporter timeout: bounded degradation and local evidence retention.
- Invalid telemetry payload: reject or sanitize before export.
- Required audit event write failure: block formal promotion.
- Optional operational metric failure: continue with `DEGRADED_TELEMETRY`.
- Backend unavailable: PR #127 readiness state and bounded error code.
- Protocol mismatch: refuse comparison and emit field-level diff.
