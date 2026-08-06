# Execution Schedule

This is a gate schedule, not a calendar promise.

| Gate | Work | Parallelism | Exit criterion |
|---|---|---:|---|
| G0 | duplicate/ownership audit | 1 | no overlap or explicit stop |
| G1A | lifecycle foundation | 1 | focused static gates pass |
| G1B | clock health foundation | 1 | may run parallel with G1A |
| G1C | sandbox foundation | 1 | may run parallel with G1A/B |
| G2A | migration foundation | 1 | dependency/lock and ephemeral DB pass |
| G2B | outbox/reconciliation | 1 | migration accepted in integration checkout |
| G3A | CPU/storage fault harness | up to 4 scenarios | all required recovery gates pass |
| G3B | GPU-related fault cases | 1 GPU job | only after G3A |
| G4 | backup, supply chain, SLO | bounded PRs | separate approvals |

## Recommended execution order

```text
Day/Session 1:
  audit
  lifecycle PR implementation
  focused tests and smoke

Day/Session 2:
  clock health PR
  sandbox PR
  no provider integration

Day/Session 3:
  dependency conflict re-audit
  migration foundation
  ephemeral DB tests

Day/Session 4:
  outbox and reconciliation
  Postgres integration tests

Day/Session 5:
  target-host fault harness
  recovery report
```

The schedule pauses whenever:

- main moves;
- a same-purpose PR appears;
- root dependency files are concurrently modified;
- actionable tests fail;
- migration downgrade fails;
- evidence bytes differ from published Git blobs;
- GitHub Actions issue #58 remains pre-run and the requested gate requires CI evidence.
