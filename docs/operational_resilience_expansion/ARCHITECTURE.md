# Architecture

## 1. Context

```text
Existing forecasting/evaluation platform
        |
        +-- Strict Configuration (#121)
        +-- Runtime Certification (#123)
        +-- Data Access Ledger (#124/#129)
        +-- Trusted Evidence (#125)
        +-- API readiness (#127)
        +-- Feature Availability (#132)
        |
        v
Operational Resilience Expansion
        |
        +-- run_lifecycle
        +-- clock_health
        +-- provider_sandbox
        +-- persistence_migrations
        +-- persistence_outbox
        +-- integration_faults
```

## 2. Component boundaries

### `loto.run_lifecycle`

Owns state transitions, commands, idempotency, lease and fencing semantics, cancellation, resume, and
event-chain validation. It does not train models or perform data access.

### `loto.clock_health`

Owns parsing-neutral clock observations and policy decisions. It does not issue trusted
timestamps and does not modify Trusted Evidence statuses.

### `loto.provider_sandbox`

Owns sandbox policy, command construction, environment filtering, mount plans, and verification of
effective constraints. It does not validate model output semantics.

### `loto.persistence_migrations`

Owns Alembic configuration, migration evidence, planning, and operator commands. It does not
automatically migrate during import or startup.

### `loto.persistence_outbox`

Owns authoritative outbox records, delivery attempts, receipts, idempotent destination protocols,
and reconciliation.

### `tests.integration_faults` and `scripts/fault_harness`

Own target-host orchestration and fault evidence. They must not be imported by production runtime.

## 3. Dependency direction

```text
contracts/canonical
    ↑
run_lifecycle core
    ↑
storage protocol
    ↑
SQLAlchemy adapter
    ↑
outbox dispatcher and reconciliation
    ↑
fault harness

clock_health core ──> prediction-lock precondition adapter (later PR)
provider_sandbox core ──> Runtime Certification executor adapter (later PR)
```

Core packages must remain dependency-light. Optional database and container dependencies stay
behind extras and injected adapters.

## 4. Database model

Planned tables after migration PRs:

```text
loto_ops.run_record
loto_ops.run_event
loto_ops.idempotency_record
loto_ops.run_lease
loto_ops.outbox_message
loto_ops.delivery_attempt
loto_ops.destination_receipt
loto_ops.reconciliation_run
```

PostgreSQL is authoritative for mutable operational state. Immutable prediction, runtime, data,
and evaluation artifacts remain file/object artifacts with SHA-256 inventories.

## 5. Transaction boundaries

A state transition and its outbox message must commit in one SQL transaction. External services are
never called inside that transaction.

```text
BEGIN
  validate current revision
  validate fencing token
  insert run event
  update run projection
  insert outbox message
COMMIT
```

Dispatch happens afterward.

## 6. Concurrency model

- optimistic revision on `run_record`;
- unique `(run_id, sequence)`;
- unique semantic idempotency key;
- lease expiry checked against database time;
- monotonically increasing fencing token;
- `SELECT ... FOR UPDATE SKIP LOCKED` for dispatch on PostgreSQL;
- no claim of equivalent concurrency behavior from SQLite tests.

## 7. Security boundary

Untrusted providers never receive:

- source-control credentials;
- SSH agent;
- cloud credentials;
- database DSNs;
- MLflow tokens;
- user home;
- Docker socket;
- unrestricted network;
- writable model snapshot.

## 8. Deployment evolution

### Phase A

Pure contracts, validators, fake repositories, deterministic tests.

### Phase B

PostgreSQL adapter and Alembic migrations in an isolated target-host environment.

### Phase C

Adapter integration with one bounded workflow. Existing path remains authoritative until parity
passes.

### Phase D

Fault injection, recovery, backup/restore, monitoring, and operational certification.
