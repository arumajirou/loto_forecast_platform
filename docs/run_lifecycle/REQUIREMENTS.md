# Requirements

## Functional requirements

| ID | Requirement | Implementation evidence |
|---|---|---|
| RLC-001 | Keep phase and status as separate enums. | `RunPhase`, `RunStatus` |
| RLC-002 | Reject unknown transitions and immutable terminal mutation. | `TransitionEngine` |
| RLC-003 | Enforce expected revision optimistic concurrency. | decision engine and repository commit |
| RLC-004 | Keep one centralized machine-readable transition matrix. | `TRANSITION_RULES`, JSON config |
| RLC-005 | Store one-based, gap-free, append-only hash-chained events. | `RunEvent`, `verify_event_chain` |
| RLC-006 | Detect reorder, deletion, insertion, tamper and Run ID drift. | event-chain validator tests |
| RLC-007 | Generate semantic idempotency keys from canonical JSON. | `idempotency.py` |
| RLC-008 | Never execute a duplicate semantic handler again. | `LifecycleService.execute` |
| RLC-009 | Reject one declared key used by different semantic payloads. | fingerprint conflict gate |
| RLC-010 | Support acquire, renew, heartbeat, expiry and takeover. | `LeaseManager` |
| RLC-011 | Reject stale-worker mutations with monotonic fencing. | lease and repository gates |
| RLC-012 | Rebuild aggregate state from immutable prior events. | `replay_events` |
| RLC-013 | Preserve sealed output hashes and avoid regeneration. | requested-output guard |
| RLC-014 | Record resume as an event and reject resume after terminal states. | transition matrix and tests |
| RLC-015 | Use opaque evidence references for external contracts. | `EvidenceReference` |
| RLC-016 | Produce machine-readable validation reports and snapshots. | validation and snapshot models |

## Strict validation requirements

All evidence models use strict, frozen Pydantic v2 configuration with unknown-field rejection,
default validation and non-finite-number rejection. Contracts reject implicit coercion, Boolean to
integer confusion, naive/non-UTC datetime values, uppercase or malformed SHA-256 strings, unsafe
identifiers and mutable collection defaults.

## Non-functional requirements

- deterministic canonical JSON;
- injected clock at the core boundary;
- no direct PostgreSQL, MLflow, API, Registry, Promotion or worker integration;
- no root dependency or workflow change;
- no protected data access;
- explicit `PARTIALLY_VERIFIED` status for unexecuted distributed/durable infrastructure claims.
