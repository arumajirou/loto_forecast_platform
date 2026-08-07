# Platform Metrics v1 Contract

## Status

```text
STACKED_ON_PR_147
COLLECTOR_FOUNDATION_ONLY
APPLICATION_WIRING_DEFERRED
GRAFANA_NOT_PROBED
```

## Scope

This increment materializes the exporter-neutral metric declarations introduced by PR #141 as
concrete, isolated `prometheus_client` collectors. It is stacked after PR #147 to preserve the planned
observability sequence, but it does not require a global OpenTelemetry provider and does not modify the
OpenTelemetry implementation.

The package is:

```text
loto.telemetry.prometheus
```

It does not modify the existing FastAPI `/metrics` endpoint, the global Prometheus registry, PR #127's
health/readiness collectors, or any production model/data/evaluation callsite.

## Collector ownership

`PrometheusMetricSet` always constructs collectors in an explicit isolated `CollectorRegistry` unless a
caller supplies another isolated registry. Construction never registers collectors in
`prometheus_client.REGISTRY`.

A later integration PR must explicitly decide how approved platform collectors and PR #127 health
collectors are combined for the application scrape endpoint. This PR does not silently change current
scrape behavior.

## Metric families

### Telemetry self-observation

```text
loto_telemetry_events_total{component,status}
loto_telemetry_dropped_total{reason}
loto_telemetry_buffer_size
```

### Pipeline

```text
loto_pipeline_runs_total{stage,status}
loto_pipeline_stage_duration_seconds{stage,status}
loto_pipeline_active_runs{stage}
loto_pipeline_last_success_timestamp_seconds{stage}
```

### Model runtime

```text
loto_model_inference_total{provider,status,device}
loto_model_inference_duration_seconds{provider,device,horizon}
loto_model_load_duration_seconds{provider,device}
loto_model_cpu_fallback_total{provider}
loto_model_output_nonfinite_total{provider}
loto_model_replay_mismatch_total{provider}
```

### Evaluation

```text
loto_evaluation_runs_total{game,status}
loto_evaluation_hit_at_1{game,position,split}
loto_evaluation_all_positions_hit_at_1{game,split}
loto_evaluation_mae{game,position,split}
loto_evaluation_worst_seed_hit_at_1{game,split}
loto_evaluation_protocol_mismatch_total{game}
loto_evaluation_leakage_sentinel_total{game,result}
```

Hit@±1 is represented directly as a bounded ratio in `[0, 1]`. The catalog does not rename the primary
metric to MAE and does not expose seed IDs as labels.

### Data

```text
loto_data_rows{game,role}
loto_data_last_observation_timestamp_seconds{game}
loto_data_missing_values{game,column_group}
loto_data_duplicate_rows{game}
loto_data_order_violations_total{game}
loto_data_future_access_blocked_total{stage}
```

### Registry, artifacts and prediction lock

```text
loto_registry_operations_total{operation,status}
loto_artifact_integrity_failure_total{artifact_type}
loto_prediction_lock_verification_total{status}
```

## Label policy

Every label has a finite allowlist. The prohibited label inventory inherited from PR #141 remains
forbidden:

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

Run, request and trace correlation belongs in structured events, traces and MLflow tags, not Prometheus
labels.

Horizon is bucketed to:

```text
1
2_7
8_31
32_plus
```

Unknown model providers or games use the bounded `unknown` label. The original provider/game identity
must remain in logs, traces or run metadata when needed for diagnosis.

## Value policy

- counters and histograms reject negative values;
- all values reject NaN and Infinity;
- row/count gauges require integer values;
- Hit@±1 gauges reject values outside `[0, 1]`;
- metric kind mismatches are rejected;
- missing, extra or unapproved labels are rejected;
- batch updates are fully validated before any collector mutation.

## Histogram buckets

Reviewed seconds buckets are committed for:

```text
pipeline stage duration
model inference duration
model load duration
```

The catalog rejects missing, duplicate or unsorted histogram buckets through the PR #141 metric
contract.

## Failure behavior

Invalid metric updates fail before mutation. Prometheus metrics are operational telemetry and do not
replace immutable audit evidence. A metric-write failure must not be represented as a successful audit
write or a successful prediction lock.

## Rollback

Before merge, close the stacked Draft PR. After merge, revert normally. No dependency, lockfile,
workflow, database, data, deployment or historical-artifact migration exists.
