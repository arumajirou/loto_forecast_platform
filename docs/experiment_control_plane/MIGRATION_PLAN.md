# Migration Plan

## Stage 1 — shadow governance

- Introduce Plan contracts without changing current experiment commands.
- Create Plans for new experiments only.
- Compare planned fields with current configs and Run artifacts.
- Record gaps without blocking legacy execution.

## Stage 2 — intake and projection

- Add Issue Form and templates.
- Create Project views as a projection.
- Do not use labels/Project fields as authorization.

## Stage 3 — agent shadow mode

- Local Agent generates a dispatch plan but does not execute.
- Compare generated command with current operator command.
- Enable one local CPU smoke experiment.
- Add one GPU smoke after CPU safety.

## Stage 4 — evidence index

- Index one existing verified Run.
- Compare GitHub summary with MLflow/PostgreSQL/Object Storage.
- Add result PR generation.
- Retain the existing evidence path until parity passes.

## Stage 5 — protected lanes

- Introduce paid API budgets.
- Introduce protected Holdout and Prospective scopes.
- Integrate Promotion Governance only in a separate later PR.

## Rollback

Each feature has an independent feature flag or operational disable procedure. Rollback never
deletes formal plans, approvals, execution events, or evidence indexes.
