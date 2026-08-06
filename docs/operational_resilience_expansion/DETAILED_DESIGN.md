# Detailed Design

## 1. Durable Run Lifecycle

### 1.1 Aggregate

`RunAggregate` is reconstructed from an ordered event list. A mutable projection may be stored for
efficient reads, but the event chain is authoritative.

Fields:

```text
run_id
workflow_type
phase
status
revision
last_sequence
last_event_sha256
active_lease_id | null
fencing_token
cancel_requested
required_evidence_kinds[]
completed_evidence_references[]
created_at_utc
updated_at_utc
```

### 1.2 Idempotency

The semantic idempotency key is the SHA-256 of canonical:

```text
schema_version
run_id
command_type
phase
expected_revision
subject_hashes
parameters
```

Timestamps, PID, lease ID, attempt number, and trace ID are excluded.

### 1.3 Lease and fencing

- acquiring an expired or empty lease increments `fencing_token`;
- renewal keeps the same token;
- every mutating command includes the token;
- storage rejects a token lower than the current token;
- local wall clock is not authoritative for a PostgreSQL lease; use database time;
- in-memory tests simulate time through an injected clock.

### 1.4 Transition matrix

Examples:

```text
PLAN/PENDING          -> PLAN/RUNNING
PLAN/RUNNING          -> PLAN/SUCCEEDED
TRAIN/RUNNING         -> TRAIN/RETRYABLE_FAILURE
PERSIST/RETRYABLE_FAILURE -> PERSIST/RUNNING
WAIT_ACTUAL/BLOCKED   -> WAIT_ACTUAL/RUNNING
*/RUNNING             -> */CANCELLED only with cancellation command
*/TERMINAL_FAILURE    -> no transition
COMPLETE/SUCCEEDED    -> no transition
```

The complete matrix is machine-readable and tested exhaustively.

## 2. Clock Health

### 2.1 Parser boundary

Parsers may support `chronyc tracking`, `chronyc sources -v`, or a JSON probe, but policy evaluation
receives a normalized `ClockObservation`.

Raw text is hashed before parsing. Parser version and code hash are retained.

### 2.2 Monotonic check

Two samples may include:

```text
wall_delta_ns
monotonic_delta_ns
difference_ns = abs(wall_delta_ns - monotonic_delta_ns)
```

A large unexplained difference is `clock_step_detected=true` and blocks Prediction Lock until a
fresh stable window passes.

## 3. Sandbox

### 3.1 Mount plan

Every mount has:

```text
source_path
target_path
mode = READ_ONLY | READ_WRITE_TMP
kind = REPOSITORY | MODEL_SNAPSHOT | INPUT | OUTPUT | TMPFS
source_sha256 | null
required
```

No source may be a symlink. Source and target containment are verified.

### 3.2 Environment plan

Allowed examples:

```text
PYTHONPATH
PYTHONDONTWRITEBYTECODE
HF_HUB_OFFLINE
TRANSFORMERS_OFFLINE
CUDA_VISIBLE_DEVICES
OMP_NUM_THREADS
MKL_NUM_THREADS
```

Patterns containing `TOKEN`, `SECRET`, `PASSWORD`, `KEY`, `DSN`, `AWS_`, `GCP_`, `AZURE_`,
`SSH_`, or `DOCKER_` are denied unless a later reviewed policy explicitly permits a non-secret
value.

### 3.3 Effective evidence

The verifier compares requested controls against observed launcher evidence. Missing observation
does not imply the control was active.

## 4. Migration foundation

### 4.1 Dependency

Main currently declares SQLAlchemy and psycopg in the `postgres` and `full` extras, but not
Alembic. The migration PR must re-audit this fact and, if unchanged, add a bounded Alembic
dependency and regenerate `uv.lock` once.

### 4.2 Safety

- no application auto-upgrade;
- no destructive revision in v1;
- no stamping an unknown production database as current;
- legacy schema inventory remains `UNADOPTED`;
- offline SQL is reviewed before target apply;
- migration script hash is retained.

### 4.3 Test databases

- SQLite: syntax and basic upgrade/downgrade smoke only;
- PostgreSQL: authoritative transactional and schema behavior;
- dialect differences are explicit.

## 5. Outbox

### 5.1 Message

```text
message_id
run_id
topic
semantic_key
payload_sha256
payload_json
required_destinations[]
status
available_at_utc
attempt_count
claimed_by
claim_expires_at
fencing_token
created_at_utc
updated_at_utc
```

### 5.2 Receipt

```text
receipt_id
message_id
destination
destination_object_id
destination_version
destination_payload_sha256
verified_at_utc
verifier_id
status
```

A self-reported destination success without a read-back hash is not a verified receipt.

### 5.3 Reconciliation outcomes

```text
CONSISTENT
MISSING_DESTINATION
ORPHAN_DESTINATION
HASH_CONFLICT
DUPLICATE_RECEIPT
RETRY_SCHEDULED
MANUAL_REVIEW_REQUIRED
```

Hash conflict is never automatically overwritten.

## 6. Fault Harness

The scenario document is frozen before execution. Each scenario records:

```text
scenario_id
preconditions
fault_action
start_trigger
duration
expected_intermediate_state
expected_final_state
timeout
cleanup
required_artifacts
```

The harness retains its own result and the application result separately:

```text
fault_injection_status
application_detection_status
application_recovery_status
data_integrity_status
reconciliation_status
```
