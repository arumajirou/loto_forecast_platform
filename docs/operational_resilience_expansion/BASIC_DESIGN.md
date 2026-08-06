# Basic Design

## 1. PR decomposition

| Order | Branch | Scope | Dependency |
|---:|---|---|---|
| 1 | `feat/durable-run-lifecycle-contract-v1` | pure contracts, validator, in-memory repository | latest main |
| 2 | `feat/clock-health-gate-v1` | injected observations and policy decision | latest main |
| 3 | `feat/untrusted-provider-sandbox-contract-v1` | sandbox plan and verifier | latest main |
| 4 | `feat/database-migration-foundation-v1` | Alembic control plane | root dependency audit |
| 5 | `feat/persistence-outbox-reconciliation-v1` | SQL tables, dispatcher, reconciliation | migration foundation |
| 6 | `test/target-host-fault-harness-v1` | real ephemeral services and failure injection | lifecycle + outbox |

Each PR remains Draft. No implementation PR may be started without a fresh duplicate and ownership
audit.

## 2. Package layout

```text
src/loto/
  run_lifecycle/
    contracts.py
    statuses.py
    transitions.py
    canonical.py
    idempotency.py
    leases.py
    repository.py
    service.py
    validator.py

  clock_health/
    contracts.py
    policy.py
    parsers.py
    service.py

  provider_sandbox/
    contracts.py
    environment.py
    mounts.py
    command_builder.py
    verifier.py

  persistence_migrations/
    contracts.py
    cli.py
    evidence.py
    verifier.py

  persistence_outbox/
    contracts.py
    protocols.py
    models.py
    repository.py
    dispatcher.py
    reconciliation.py

tests/
  run_lifecycle/
  clock_health/
  provider_sandbox/
  persistence_migrations/
  persistence_outbox/
  integration/faults/

migrations/
  env.py
  script.py.mako
  versions/

scripts/
  run_clock_health_check.py
  run_provider_sandbox.py
  manage_database_migrations.py
  run_outbox_dispatcher.py
  run_reconciliation.py
  run_fault_harness.py
```

Final names must be confirmed against the repository before implementation.

## 3. Common coding rules

- Python `>=3.11,<3.14`;
- uv and checked lockfile;
- Pydantic v2 strict frozen evidence;
- Protocol-based I/O;
- no shell interpolation;
- atomic file writes;
- complete SHA256SUMS;
- safe relative paths;
- structured errors;
- no broad exception-to-PASS fallback;
- no hidden network calls;
- no import-time side effects.

## 4. Integration policy

The first PR for each subsystem is adoption-neutral. Integration is a later, bounded PR:

- lifecycle → one research or Prospective control path;
- clock health → Prediction Lock preflight;
- sandbox → one remote-code provider;
- migrations/outbox → one persistence workflow;
- fault harness → that integrated workflow.

Provider-local logic remains until parity is demonstrated.

## 5. Operational statuses

```text
NOT_CONFIGURED
PENDING
PARTIALLY_VERIFIED
VERIFIED
BLOCKED
RECONCILIATION_REQUIRED
FAILED
REVOKED
```

Subsystem-specific statuses remain separate. A runtime PASS cannot be reused as an accuracy,
persistence, clock, sandbox, or recovery PASS.
