# Requirements

## 1. Goals

### G-1 Durable execution

A run must survive process restart without repeating irreversible actions or changing prediction
bytes already sealed before Actual values are known.

### G-2 Exactly-once effect, at-least-once delivery

External delivery may be retried, but each semantic command and destination effect must be
deduplicated through an idempotency key, destination receipt, and fencing token.

### G-3 Fail-closed chronology

No lifecycle retry, reconciliation job, migration, clock-health decision, sandbox run, or fault
test may open Holdout or Prospective actuals implicitly.

### G-4 Evidence-first operations

Each transition, retry, lease, migration, delivery attempt, clock decision, sandbox policy, and
fault observation must produce strict machine-readable evidence and a canonical SHA-256.

## 2. Functional requirements

### Durable Run Lifecycle

- **FR-DL-001**: Represent phase and status separately.
- **FR-DL-002**: Reject unknown transitions.
- **FR-DL-003**: Persist append-only transition events with gap-free sequence numbers.
- **FR-DL-004**: Require one deterministic idempotency key per semantic command.
- **FR-DL-005**: Implement lease ownership, lease expiry, heartbeat, and monotonically increasing
  fencing tokens.
- **FR-DL-006**: Reject writes from a stale fencing token.
- **FR-DL-007**: Distinguish retryable, blocked, cancelled, timed-out, and terminal failures.
- **FR-DL-008**: Support resume without rewriting prior immutable outputs.
- **FR-DL-009**: Require explicit cancellation and prevent post-cancellation continuation.
- **FR-DL-010**: Record required evidence references without copying schemas owned by other PRs.

### Clock Health

- **FR-CH-001**: Accept injected clock observations; core logic must not execute shell commands.
- **FR-CH-002**: Evaluate synchronization state, UTC offset magnitude, root dispersion, stratum,
  source count, leap status, sample age, and monotonic-clock continuity.
- **FR-CH-003**: Return `HEALTHY`, `DEGRADED`, `BLOCKED`, or `UNKNOWN`.
- **FR-CH-004**: Block a Prediction Lock precondition when policy thresholds fail.
- **FR-CH-005**: Never convert a healthy local clock into externally trusted time.
- **FR-CH-006**: Retain raw observation hash and parser identity.

### Provider Sandbox

- **FR-SB-001**: Build argv arrays without shell interpolation.
- **FR-SB-002**: Default to network disabled, read-only root, read-only model snapshot, no new
  privileges, all capabilities dropped, bounded PIDs, memory, CPU, output bytes, and wall time.
- **FR-SB-003**: Permit only allowlisted environment variables and mounted paths.
- **FR-SB-004**: Reject secret-bearing environment variables.
- **FR-SB-005**: Reject `NONE` as a valid backend for untrusted remote code.
- **FR-SB-006**: Verify requested and effective sandbox policy from retained evidence.
- **FR-SB-007**: Keep runtime-certification semantics in PR #123; the sandbox only constrains
  execution.

### Database Migration

- **FR-MG-001**: Use Alembic with SQLAlchemy 2.x after dependency and lock verification.
- **FR-MG-002**: Require explicit `check`, `plan`, `upgrade`, and `downgrade` operations.
- **FR-MG-003**: Never auto-upgrade during application import or API startup.
- **FR-MG-004**: Retain migration revision, previous revision, script SHA-256, SQL preview hash,
  operator, start/end time, and result.
- **FR-MG-005**: Support offline SQL generation.
- **FR-MG-006**: Detect divergent heads and missing migrations.
- **FR-MG-007**: Classify the current legacy schema as unadopted until inspected.
- **FR-MG-008**: Verify upgrade/downgrade in ephemeral databases before target-host apply.

### Outbox and Reconciliation

- **FR-OR-001**: Create an outbox message in the same database transaction as the authoritative
  state change.
- **FR-OR-002**: Maintain destination-specific delivery attempts and receipts.
- **FR-OR-003**: Enforce unique semantic idempotency keys.
- **FR-OR-004**: Support retry with bounded exponential backoff and a terminal poison state.
- **FR-OR-005**: Detect missing destination records, orphan artifacts, hash conflicts, and duplicate
  receipts.
- **FR-OR-006**: Require reconciliation before a run is marked fully persisted.
- **FR-OR-007**: Never delete failed evidence automatically.
- **FR-OR-008**: Expose protocol interfaces for PostgreSQL, MLflow, Parquet, and artifact storage
  without requiring live services in the foundation PR.

### Fault Harness

- **FR-FH-001**: Start real ephemeral PostgreSQL and network fault proxies on a target host.
- **FR-FH-002**: Inject latency, timeout, connection reset, service unavailability, duplicate
  execution, process kill after commit, and restart.
- **FR-FH-003**: Verify no duplicate semantic effect and eventual reconciliation.
- **FR-FH-004**: Preserve commands, container/image identities, timings, logs, reports, and hashes.
- **FR-FH-005**: Separate harness success from application recovery success.
- **FR-FH-006**: Produce a deterministic scenario inventory before execution.
- **FR-FH-007**: Run GPU fault cases serially and only after CPU/storage cases pass.

## 3. Forecasting and evaluation requirements

Operational changes must not alter forecasting metrics. Any later predictive evaluation must retain:

- primary metric: Hit@±1;
- MAE, MSE, RMSE;
- position-level and all-position Hit@±1;
- Random, fixed, mean, median, last, frequency, and approved statistical baselines;
- chronological Train, Validation, Holdout, Prospective separation;
- Train-only scaler, encoder, feature selection, and HPO;
- all approved seeds, mean, population variance, and worst value;
- no best-seed-only adoption;
- SHA-256 and timestamp prediction lock before Actual values.

## 4. Non-functional requirements

- **NFR-001 Strictness**: Pydantic v2 `extra="forbid"`, strict types, frozen evidence models,
  finite numeric values, timezone-aware UTC.
- **NFR-002 Determinism**: canonical JSON; sorted keys; stable separators; UTF-8; explicit list
  ordering.
- **NFR-003 Integrity**: all persisted evidence has SHA-256 and complete manifest accounting.
- **NFR-004 Security**: no secrets in logs, artifacts, exception text, process argv, or environment
  inventories.
- **NFR-005 Compatibility**: Python 3.11–3.13; Linux target host; Windows launch instructions where
  feasible.
- **NFR-006 Testability**: pure core logic and injected I/O protocols.
- **NFR-007 Observability**: bounded status taxonomy and low-cardinality metrics when integrated.
- **NFR-008 Safety**: no direct main write, force push, auto-merge, branch deletion, or protected
  data access.
- **NFR-009 Performance**: focused tests first; CPU thread cap 8; one GPU job at a time.
- **NFR-010 Recovery**: every irreversible operation has either idempotent replay or explicit
  compensation/reconciliation.

## 5. Out of scope for the first six PRs

- Temporal or Dagster production deployment
- OPA, Keycloak, Feast, or a new custom UI
- production RFC3161 or Sigstore verifier
- model implementation or provider migration
- Holdout opening or Prospective Actual access
- automatic model registration or promotion
- production backup deletion or destructive restore
