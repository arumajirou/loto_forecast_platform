# Data Contract

## Common validation

All formal JSON/YAML-derived contracts:

- Pydantic v2 strict and frozen;
- `extra="forbid"`;
- finite numbers;
- timezone-aware UTC;
- lowercase 64-character SHA-256;
- safe identifiers and relative paths;
- duplicate JSON key rejection;
- canonical UTF-8 serialization;
- no credential-bearing URI.

## ExperimentPlan

Required sections:

```text
identity
hypothesis
code_binding
data_bindings[]
model_bindings[]
execution
seed_policy
evaluation
baseline_inventory
search_budget
resource_budget
protected_stages
required_evidence[]
non_claims[]
experiment_plan_sha256
```

## Evaluation contract

```text
primary_metric = HIT_AT_1
secondary_metrics =
  POSITION_HIT_AT_1
  ALL_POSITIONS_HIT_AT_1
  MAE
  MSE
  RMSE

best_seed_only_selection = false
first_place_only_selection = false
```

Baseline inventory must include:

```text
RANDOM
FIXED
MEAN
MEDIAN
LAST
FREQUENCY
STATISTICAL
```

## Approval record

An approval is valid only when:

- plan hash matches;
- scope matches;
- approver is authorized;
- approval is unexpired;
- one-time approval has not been consumed;
- conditions are satisfied;
- approval integrity verifies.

## EvidenceIndexEntry

```text
artifact_type
artifact_id
uri
size_bytes
sha256
media_type
producer
created_at_utc
source_system
verification_status
retention_class
sensitivity
metadata_sha256
```

## ProjectProjection

Projection fields are optional and non-authoritative. Every projection includes the source formal
object SHA and update sequence.

## BudgetLedger

```text
max_api_cost
reserved_api_cost
actual_api_cost
max_gpu_hours
reserved_gpu_hours
actual_gpu_hours
request_count
input_tokens
output_tokens
currency
pricing_snapshot_id
```

Unknown or stale pricing blocks formal cost verification.
