# Data Contract

## 1. General rules

All JSON contracts:

- reject duplicate keys;
- reject NaN and infinity;
- require lowercase 64-character SHA-256;
- require timezone-aware UTC timestamps;
- reject unsafe paths and symlinks;
- use Pydantic v2 strict validation;
- include explicit schema version;
- never treat notes or operator booleans as independent proof.

## 2. `RunCommand`

| Field | Type | Rule |
|---|---|---|
| schema_version | literal | `1.0.0` |
| command_id | identifier | unique |
| run_id | identifier | immutable |
| command_type | enum | bounded |
| expected_revision | integer | non-negative |
| phase | enum | required |
| fencing_token | integer | positive for mutation |
| subject_hashes | list[SHA256] | sorted and unique |
| parameters | object | strict command-specific schema |
| idempotency_key | SHA256 | recomputed by validator |
| requested_at_utc | datetime | evidence only |

## 3. `RunEvent`

The event hash excludes only `event_sha256`. It includes the previous event hash, preserving chain
order. Sequence starts at 1 and is gap-free.

## 4. `RunLease`

```text
lease_id
run_id
owner_id
fencing_token
acquired_at_utc
heartbeat_at_utc
expires_at_utc
database_time_observed_at_utc | null
```

`expires_at_utc` must be after heartbeat and acquisition. Production SQL adapters use database time.

## 5. `ClockObservation`

Values use SI seconds and explicit sign. `last_offset_seconds` retains the source sign; policy uses
its absolute value where required.

## 6. `ClockHealthDecision`

```text
decision_id
observation_sha256
policy_sha256
status
failed_checks[]
warning_checks[]
clock_step_detected
prediction_lock_allowed
evaluated_at_utc
decision_sha256
```

`prediction_lock_allowed=true` is possible only for `HEALTHY`.

## 7. `SandboxPolicy`

```text
policy_id
backend
untrusted_remote_code
network_mode
root_filesystem
mounts[]
environment_allowlist[]
environment_deny_patterns[]
cpu_limit
memory_limit_bytes
pids_limit
file_size_limit_bytes
output_limit_bytes
wall_timeout_seconds
gpu_devices[]
no_new_privileges
drop_all_capabilities
seccomp_profile_sha256 | null
policy_sha256
```

## 8. `MigrationEvidence`

```text
operation_id
database_identity_hash
operation
from_revision
to_revision
migration_script_hashes[]
offline_sql_sha256 | null
operator
approved
started_at_utc
completed_at_utc | null
status
error_code | null
evidence_sha256
```

Credentials and raw DSNs are forbidden.

## 9. `OutboxMessage`

The canonical payload is stored as strict JSON. The payload hash is verified on every claim and
delivery. Required destinations are ordered and unique.

## 10. `DeliveryAttempt`

```text
attempt_id
message_id
destination
attempt_number
worker_id
fencing_token
started_at_utc
completed_at_utc
outcome
retry_at_utc | null
response_metadata_hash | null
error_code | null
```

Raw exception strings are not persisted.

## 11. `DestinationReceipt`

A verified receipt requires destination read-back or an equivalent immutable acknowledgment bound
to the payload hash.

## 12. `FaultScenarioResult`

The result must retain both expected and observed states. A harness that successfully creates a
fault does not imply application recovery.
