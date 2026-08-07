# Architecture

```text
RunCommand
   |
   v
LifecycleService -- semantic key --> IdempotencyRecord
   |                    |
   | duplicate          +--> previous verified result
   v
LeaseManager --> injected Clock --> RunLease/fencing gate
   |
   v
TransitionEngine --> centralized TransitionRule matrix
   |
   v
RunEvent builder --> canonical hash chain
   |
   v
InMemoryLifecycleRepository
   |-- events (append-only tuple)
   |-- aggregate (revision CAS)
   |-- idempotency record
   `-- active lease and fencing counter

replay_events(events) --> reconstructed RunAggregate
validate_lifecycle(events) --> LifecycleValidationReport
```

## Atomicity boundary

The repository uses one in-process lock to atomically commit the event, aggregate and idempotency
record. The service uses a lock to prevent duplicate handler execution within one service instance.
This is deliberately weaker than a transactional database and distributed lock. A future database
adapter must preserve the same compare-and-swap and unique-idempotency semantics transactionally.

## Dependency direction

The package has no imports from model providers, Runtime Certification, Data Access Ledger, Trusted
Evidence, Feature Availability, Evaluation, API, Registry or Promotion packages. Cross-domain
proof is represented only through `EvidenceReference`.

## Clock boundary

`SystemClock` is an adapter. Core logic accepts the `Clock` protocol; tests and replay simulations
use `ManualClock`. Lease code and service code do not call `datetime.now()` directly.
