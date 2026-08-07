# Test Plan

## 1. Test strategy

Run in this order:

```text
schema/unit
→ property/negative
→ focused package
→ compileall
→ Ruff
→ mypy
→ smoke
→ integration
→ fault injection
→ full pytest
→ actionable CI
```

Heavy full pytest is last.

## 2. Durable lifecycle tests

- strict unknown field and type rejection;
- canonical idempotency key stability;
- different semantic command changes key;
- complete valid transition matrix;
- every invalid transition fails;
- event sequence gap/reorder/duplicate rejection;
- previous hash tamper rejection;
- duplicate command returns prior result;
- lease expiry and takeover;
- fencing token increases;
- stale worker mutation rejected;
- heartbeat after expiry rejected;
- cancellation prevents continuation;
- terminal state is immutable;
- resume does not regenerate sealed output hash;
- property-based state-machine tests.

## 3. Clock health tests

- synchronized healthy fixture;
- unsynchronized block;
- excessive offset block;
- excessive dispersion block;
- stale sample block;
- degraded warning threshold;
- malformed parser input becomes `UNKNOWN`;
- duplicate input fields rejected;
- monotonic/wall clock step detection;
- local health never maps to external trusted status;
- raw observation tamper rejection.

## 4. Sandbox tests

- command builder produces argv, not shell;
- network disabled by default;
- read-only repository/model mounts;
- output path is isolated and writable;
- symlink/path traversal rejection;
- secret environment rejection;
- no Docker socket/SSH agent/home mount;
- untrusted code with backend `NONE` rejected;
- CPU/memory/PID/time limits required;
- GPU device allowlist;
- effective evidence missing control fails closed;
- fake child timeout and non-zero exit.

## 5. Migration tests

- Alembic heads exactly one;
- revision IDs unique;
- migration script checksum inventory;
- offline SQL generation;
- empty DB upgrade to head;
- head downgrade to base;
- upgrade again after downgrade;
- existing unknown schema not auto-stamped;
- no import-time migration;
- DSN redaction;
- failure evidence persistence;
- PostgreSQL test where Docker is available.

## 6. Outbox tests

- state and outbox commit together;
- rollback leaves neither;
- unique semantic key;
- one message, multiple required destinations;
- partial delivery remains incomplete;
- verified receipt completes destination;
- duplicate receipt rejected;
- retry schedule;
- poison message after maximum attempts;
- process kill after commit;
- stale dispatcher fencing rejected;
- orphan destination detection;
- missing destination detection;
- hash conflict requires manual review;
- reconciliation is idempotent;
- concurrent claim with PostgreSQL `SKIP LOCKED`.

## 7. Fault tests

- duplicate command;
- process kill after authoritative commit;
- PostgreSQL temporary loss;
- destination timeout;
- connection reset;
- restart and resume;
- stale lease writer;
- corrupted artifact;
- clock unhealthy precondition;
- sandbox network denial.

## 8. Forecasting safety regression

The operational work must not change:

- Hit@±1 implementation;
- MAE/MSE/RMSE;
- baseline definitions;
- split chronology;
- protocol hash;
- Data Access Ledger semantics;
- prediction-lock bytes;
- runtime-certification output semantics.

## 9. Required reports

```text
FOCUSED_TEST_REPORT.json
STATIC_ANALYSIS_REPORT.json
SMOKE_REPORT.json
INTEGRATION_REPORT.json
FAULT_INJECTION_REPORT.json
RECOVERY_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

Unavailable checks remain `BLOCKED` or `NOT_EXECUTED`, never `PASS`.
