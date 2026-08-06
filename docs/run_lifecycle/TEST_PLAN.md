# Test Plan

## Focused suites

| Area | Required cases |
|---|---|
| Strict models | unknown fields, coercion, bool/int, UTC, SHA, identifiers, frozen models |
| Transition engine | valid matrix, unknown transition, revision mismatch, terminal immutability |
| Event chain | normal replay, reorder, delete, insert, payload tamper, phase tamper |
| Idempotency | duplicate result reuse, handler call count, declared-key conflict |
| Cancellation | explicit cancel, exact duplicate cancel, resume rejection |
| Lease/fencing | acquire, renew, heartbeat, expiry, takeover, wrong owner, stale token |
| Recovery | restart-equivalent replay and sealed output preservation |
| Full lifecycle | PLAN through COMPLETE/SUCCEEDED and post-completion rejection |
| Configuration | JSON transition matrix equals code matrix |
| Property tests | canonical determinism and changed-payload hash difference |
| Import | package imports without optional runtime dependencies |

## Commands

```bash
PYTHONPATH=src python -m pytest -q tests/run_lifecycle
python -m compileall -q src/loto/run_lifecycle tests/run_lifecycle
```

## Deferred gates

- complete repository regression suite;
- Ruff and mypy in an environment containing the repository development dependencies;
- database transaction/failure-injection tests;
- multi-process race and crash-recovery tests;
- production worker integration;
- GitHub Actions after the repository runner starts jobs normally.
