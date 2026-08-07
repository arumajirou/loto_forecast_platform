# Data Contract

The examples below are normative field sets for design review. Implementation must publish strict JSON Schema and Pydantic models in an independent PR.

## ExperimentPlan v1

```yaml
schema_version: "1.0.0"
experiment_id: "EXP-20260806-0001"
title: "Numbers4 AutoModel bounded comparison"
source:
  issue_number: 201
  repository: "arumajirou/loto_forecast_platform"
  code_commit: "<40-char immutable SHA>"
  plan_path: "experiments/plans/EXP-20260806-0001.yaml"
identity:
  config_sha256: "<64 hex>"
  data_snapshot_sha256: "<64 hex>"
  protocol_hash: "<64 hex>"
  model_id: "<catalog model id>"
  model_revision: "<immutable revision>"
data_split:
  train_end: "<ordered boundary>"
  validation_end: "<ordered boundary>"
  holdout_start: "<ordered boundary>"
  prospective_start: "<ordered boundary or null>"
execution:
  lane: "local-gpu"
  host_profile: "rtx-5070ti-16gb"
  seeds: [1, 7, 19]
  max_runtime_seconds: 21600
  max_retries: 1
  network_policy: "preloaded-only"
evaluation:
  primary_metric: "hit_at_1"
  secondary_metrics: ["mae", "mse", "rmse", "position_hit_at_1", "all_positions_hit_at_1"]
  baselines: ["random", "fixed", "mean", "median", "last", "frequency", "statistical"]
  oof_required: true
  multi_seed_required: true
budget:
  max_gpu_hours: 6.0
  max_api_cost_usd: 0.0
  max_trials: 100
gates:
  holdout_allowed: false
  prospective_allowed: false
  prediction_lock_required: true
  runtime_certification_required: true
evidence:
  object_store_profile: "local-content-addressed-v1"
  mlflow_experiment: "loto-experiments"
  retention_class: "research-formal"
plan_sha256: "<derived 64 hex>"
```

## ApprovalRecord v1

```json
{
  "schema_version": "1.0.0",
  "approval_id": "APR-...",
  "subject_sha256": "<64 hex>",
  "scope": "EXECUTE",
  "decision": "APPROVE",
  "actor": {"type": "github_user", "id": "arumajirou"},
  "policy_version": "experiment-approval-v1",
  "reason": "Approved bounded local GPU execution",
  "issued_at": "2026-08-06T09:30:00Z",
  "expires_at": "2026-08-07T09:30:00Z",
  "previous_event_sha256": "<64 hex or null>",
  "record_sha256": "<derived 64 hex>"
}
```

## ExecutionRequest v1

```json
{
  "schema_version": "1.0.0",
  "request_id": "REQ-...",
  "run_id": "RUN-...",
  "experiment_id": "EXP-20260806-0001",
  "plan_sha256": "<64 hex>",
  "approval_id": "APR-...",
  "approval_subject_sha256": "<64 hex>",
  "lane": "local-gpu",
  "idempotency_key": "<caller supplied stable key>",
  "requested_by": "arumajirou",
  "requested_at": "<UTC RFC3339>",
  "request_sha256": "<derived 64 hex>"
}
```

## EvidenceReference v1

```json
{
  "evidence_id": "EVD-...",
  "role": "prediction",
  "subject": {"run_id": "RUN-...", "plan_sha256": "<64 hex>"},
  "uri": "s3://bucket/content/sha256/<digest>",
  "sha256": "<64 hex>",
  "size_bytes": 123456,
  "media_type": "application/vnd.apache.parquet",
  "producer": {"component": "local-agent", "version": "<code SHA>"},
  "created_at": "<UTC RFC3339>",
  "contains_secret": false,
  "contains_raw_personal_data": false
}
```

## ResultSummary v1

```json
{
  "schema_version": "1.0.0",
  "run_id": "RUN-...",
  "experiment_id": "EXP-...",
  "plan_sha256": "<64 hex>",
  "protocol_hash": "<64 hex>",
  "prediction_lock_evidence_id": "EVD-...",
  "evaluation_evidence_id": "EVD-...",
  "metrics": {
    "hit_at_1_mean": 0.0,
    "hit_at_1_worst_seed": 0.0,
    "mae_mean": 0.0,
    "mse_mean": 0.0,
    "rmse_mean": 0.0
  },
  "verdict": "NO_MODEL_BEATS_BASELINE",
  "promotion_requested": false,
  "result_sha256": "<derived 64 hex>"
}
```

## Validation rules

- SHA-256 is lowercase 64 hexadecimal characters.
- Repository code identity is an immutable full commit SHA.
- Model revisions must be immutable; `latest`, branch-only and `UNPINNED` are rejected for formal runs.
- Seeds must be unique; a best seed cannot be the sole reported result.
- Time boundaries are strictly ordered and cannot be inferred from future data.
- URI userinfo, query credentials and embedded tokens are rejected.
- Derived hashes are recomputed, not trusted from input.
- Unknown fields are rejected.
