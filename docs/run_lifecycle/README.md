# Durable Run Lifecycle Contract v1

## Status

`EXECUTED / FOUNDATION_ONLY / FOCUSED_TESTS_PASS / PRODUCTION_DURABILITY_NOT_PROVEN`

This package adds a provider-neutral run lifecycle foundation for deterministic state transitions,
append-only event evidence, semantic idempotency, optimistic concurrency, leases, heartbeats,
fencing tokens, replay, cancellation, and immutable output preservation.

## Design provenance

- Design source: Draft PR #140, read-only
- Design branch: `docs/operational-resilience-expansion-blueprint-v1`
- Design head: `1ae5b0736a3d740a4c787e77f918d77ea35fe7a1`
- Implementation base: `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Implementation branch: `feat/durable-run-lifecycle-contract-v1`

The implementation branch is independent of the design branch.

## Package layout

```text
src/loto/run_lifecycle/
  canonical.py      deterministic JSON and SHA-256
  clock.py          injected system/manual clocks
  events.py         event creation, hashing and verification
  exceptions.py     domain failure taxonomy
  idempotency.py    semantic key and fingerprint construction
  lease.py          acquire, renew, heartbeat, takeover and fencing
  models.py         strict immutable Pydantic v2 contracts
  replay.py         aggregate reconstruction
  repository.py     atomic in-process foundation repository
  service.py        command execution and idempotent result reuse
  transitions.py    centralized machine-readable transition matrix
  validation.py     machine-readable validation report
```

## Important boundary

`InMemoryLifecycleRepository` proves contract behavior inside one Python process. It is not evidence
of PostgreSQL durability, multi-process exactly-once execution, distributed consensus, production
recovery, or deployment readiness. Database persistence and existing-pipeline integration require
separate PRs.

## Quick example

```python
from datetime import UTC, datetime

from loto.run_lifecycle import (
    CanonicalJsonObject,
    InMemoryLifecycleRepository,
    LifecycleService,
    ManualClock,
    RunCommand,
    RunCommandType,
    RunPhase,
)

clock = ManualClock(datetime(2026, 8, 6, tzinfo=UTC))
service = LifecycleService(InMemoryLifecycleRepository(), clock)
command = RunCommand(
    command_id="cmd-001",
    run_id="run-001",
    command_type=RunCommandType.START,
    phase=RunPhase.PLAN,
    expected_revision=0,
    semantic_parameters=CanonicalJsonObject.from_object({"plan": "v1"}),
    issued_at=clock.now(),
    actor_id="operator-1",
)
result = service.execute(command)
assert result.aggregate.revision == 1
```

## Verification command

```bash
PYTHONPATH=src python -m pytest -q tests/run_lifecycle
python -m compileall -q src/loto/run_lifecycle tests/run_lifecycle
```
