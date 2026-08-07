# Implementation Schedule

This is a gate-based schedule, not a promise of elapsed time.

| Phase | PRs | Entry gate | Exit gate |
|---|---|---|---|
| A Contract foundation | PR-1 to PR-3 | duplicate/ownership audit complete | strict schemas, canonical hashes, approval/evidence contracts and focused tests pass |
| B Control semantics | PR-4 | PR-1/2 and lifecycle ownership resolved | idempotent enqueue/cancel/status; no external long-running side effect |
| C Durable execution | PR-5/6 | control service contract stable | restart, lease takeover, cancellation, GPU/API lane certification evidence |
| D GitHub integration | PR-7/8 | canonical state stable; App/settings plan confirmed | projection reconciliation and short dispatch control verified |
| E Evidence integration | PR-9 | object/DB/MLflow test services available | real-service idempotency, digest and downstream handoff verified |
| F Operational certification | PR-10 | all prior contracts merged and local services healthy | end-to-end synthetic certification and rollback drill complete |

## Stop conditions

Stop the current stage when:

- the capability is already present on latest main;
- an open PR owns the same path or semantic subject;
- a required upstream contract is ambiguous or incompatible;
- a secret, raw data, Holdout/Prospective access or production mutation would be required outside scope;
- focused tests fail and the cause is not isolated;
- the local environment cannot prove a required runtime claim;
- the repository/account Actions condition remains zero-step and the only proposed action is blind rerun.

## Promotion to the next phase

A phase advances only with:

```text
implementation status recorded
local verification report
remote blob/manifest integrity check
open Draft PR with exact non-claims
owner decision on unresolved risks
```
