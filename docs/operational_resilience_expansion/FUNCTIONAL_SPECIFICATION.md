# Functional Specification

## 1. Common evidence envelope

Every new subsystem emits a common local envelope without redefining the contracts owned by open
PRs.

```text
schema_version
evidence_id
run_id
created_at_utc
producer
code_sha256
config_sha256 | null
input_sha256
payload_sha256
status
non_claims[]
```

The envelope may reference, but must not embed incompatible copies of:

- Runtime Certification evidence;
- Data Access Ledger;
- Trusted Evidence bundle;
- Feature Availability manifest;
- Prediction Lock and Actuals Lock;
- evaluation protocol hash.

## 2. Durable lifecycle semantics

### 2.1 Phase

```text
PLAN
DATA
TRAIN
PREDICT
LOCK
WAIT_ACTUAL
READ_ACTUAL
SCORE
PERSIST
PROMOTE
COMPLETE
```

### 2.2 Status

```text
PENDING
RUNNING
SUCCEEDED
RETRYABLE_FAILURE
BLOCKED
CANCELLED
TIMED_OUT
TERMINAL_FAILURE
```

Phase and status are separate. For example, `PERSIST + RETRYABLE_FAILURE` means the forecast
computation may be complete while an external destination remains unavailable.

### 2.3 Events

A lifecycle event is append-only and contains:

```text
event_id
sequence
run_id
phase
from_status
to_status
command_id
idempotency_key
lease_id
fencing_token
occurred_at_utc
monotonic_elapsed_ns
actor
input_hashes
output_hashes
evidence_references
previous_event_sha256
event_sha256
```

### 2.4 Command processing

1. Validate strict command.
2. Resolve deterministic idempotency key.
3. Acquire or renew lease.
4. Compare fencing token.
5. Check current state and allowed transition.
6. Execute through an injected handler.
7. Atomically write result and event.
8. Return the previous result for an already completed idempotency key.
9. Never re-execute an irreversible handler after a successful receipt.

## 3. Clock health decision

Inputs:

```text
synchronized
leap_status
stratum
last_offset_seconds
rms_offset_seconds
root_delay_seconds
root_dispersion_seconds
frequency_skew_ppm
sources_online
sample_age_seconds
wall_clock_utc
monotonic_ns
parser_id
raw_observation_sha256
```

A policy defines thresholds. Default examples in documentation are not production authorization.
The target host must approve the effective values.

Decision rules:

- missing or unparsable evidence → `UNKNOWN`;
- unsynchronized or invalid leap status → `BLOCKED`;
- absolute offset above hard limit → `BLOCKED`;
- dispersion or sample age above hard limit → `BLOCKED`;
- warning threshold exceeded → `DEGRADED`;
- all required checks pass → `HEALTHY`.

`HEALTHY` means the host clock satisfies the operational policy. It does not mean the timestamp is
externally trusted.

## 4. Sandbox plan

### 4.1 Supported backends

```text
BUBBLEWRAP
ROOTLESS_OCI
```

`NONE` is a schema value only for trusted in-process code and is invalid when
`untrusted_remote_code=true`.

### 4.2 Required effective controls

- no network namespace access;
- read-only root;
- read-only repository and model snapshot;
- writable isolated output and tmpfs only;
- no device access except explicitly approved GPU devices;
- no host home, SSH agent, cloud credentials, Docker socket, or database credentials;
- bounded CPU, memory, PIDs, file size, open files, and wall time;
- seccomp/no-new-privileges/capability drop;
- exact command and environment allowlist.

### 4.3 Result

The sandbox launcher returns execution evidence, not model success. Runtime success remains under
the Runtime Certification SDK.

## 5. Migration workflow

```text
AUDIT
→ GENERATE_PLAN
→ REVIEW_SQL
→ EPHEMERAL_UPGRADE
→ EPHEMERAL_DOWNGRADE
→ BACKUP_CONFIRMED
→ TARGET_UPGRADE_APPROVED
→ TARGET_UPGRADE
→ POST_CHECK
```

No step may be inferred from a later successful step. `alembic current` and application startup
must never silently apply migrations.

## 6. Outbox workflow

```text
AUTHORITATIVE_TRANSACTION
  ├─ state update
  └─ outbox insert

DISPATCH
  ├─ claim with lease/fencing token
  ├─ send
  ├─ verify destination receipt
  └─ store receipt

RECONCILE
  ├─ compare expected destinations
  ├─ reopen hashes
  ├─ repair missing effects through idempotent replay
  └─ emit reconciliation report
```

A run becomes `PERSIST + SUCCEEDED` only after all required destinations have verified receipts.

## 7. Fault scenarios

Minimum formal scenario set:

| Scenario | Injection | Expected behavior |
|---|---|---|
| F01 | duplicate command | one semantic effect, same result returned |
| F02 | stale worker after lease renewal | stale fencing token rejected |
| F03 | process kill after DB commit | outbox survives; delivery resumes |
| F04 | MLflow unavailable | DB state preserved; retryable delivery |
| F05 | artifact timeout | partial destination state detected |
| F06 | connection reset during receipt | destination verification prevents duplicate |
| F07 | service restart | run resumes from persisted state |
| F08 | clock unsynchronized | prediction-lock precondition blocked |
| F09 | sandbox requests network | launch rejected or network unavailable |
| F10 | artifact tamper | reconciliation reports conflict, no automatic overwrite |

## 8. Exit codes

All new CLIs use:

```text
0 = verified success
1 = validation or operational failure
2 = correctly blocked / pending external prerequisite
3 = reconciliation required
130 = operator interruption
```
