# Implementation Plan

Each stage is an independent Draft PR from the then-current `main`. Do not create one monolithic PR.

## PR-1 Experiment Plan Contract v1

```text
branch=feat/experiment-plan-contract-v1
```

Deliver strict Plan/identity contracts, canonical hashing, JSON Schemas, validators, example plans, focused tests and docs. No database, worker, workflow, approval or execution side effects.

## PR-2 Approval Ledger v1

```text
branch=feat/experiment-approval-ledger-v1
```

Deliver ApprovalSubject/ApprovalRecord/RevocationRecord, policy evaluation, append-only repository interface, in-memory reference implementation and focused tests. No real execution authorization until durable storage is separately proven.

## PR-3 Evidence Index v1

```text
branch=feat/experiment-evidence-index-v1
```

Deliver evidence roles, strict references, content hashing, URI secret rejection, verification receipts and local content-addressed reference store. No production object-store credentials.

## PR-4 Control Service and CLI v1

```text
branch=feat/experiment-control-service-v1
```

Deliver plan validation, approval decision, idempotent enqueue/cancel/status/export service and CLI. Integrate canonical lifecycle from PR #148 if merged; otherwise stop on ownership conflict or use an explicitly temporary adapter.

## PR-5 Durable Agent Protocol v1

```text
branch=feat/local-experiment-agent-protocol-v1
```

Deliver polling client, lease/fence protocol, heartbeat, isolated workspace, bounded cancellation, local CPU smoke executor and restart tests. No GPU/API lane yet.

## PR-6 Local GPU and Paid API Lanes v1

```text
branch=feat/experiment-execution-lanes-v1
```

Deliver separate lane profiles, runtime/cost evidence adapters and secret boundaries. Reuse PR #123 and PR #146 when merged. GPU load/infer/unload/VRAM release and API budget circuit-breaker evidence are required.

## PR-7 GitHub App Projections v1

```text
branch=feat/experiment-github-projections-v1
```

Deliver Check Run/Issue/PR/Project projection adapters, deterministic outbox keys and reconciliation. Reuse PR #145's Project schema. The App has no authority to invent approvals or canonical state.

## PR-8 Short Control Workflows v1

```text
branch=feat/experiment-control-workflows-v1
```

After the required workflows can exist on default branch, add Issue/Plan validation, manual dispatch, cancel, result verification and projection synchronization. Workflows enqueue and exit; they do not host long experiments. Address Issue #58 administratively before relying on CI evidence.

## PR-9 Evidence Plane Adapters and Downstream Handoff v1

```text
branch=feat/experiment-evidence-adapters-v1
```

Integrate PostgreSQL/MLflow/object storage and the canonical downstream commit/promotion handoff without bypassing PR #151 or PR #137. Prove idempotency against real test services.

## PR-10 Operational Certification v1

```text
branch=certify/experiment-control-plane-v1
```

Run an end-to-end synthetic campaign, failure injection, restart, lease takeover, evidence corruption, projection outage and backup/restore tests. No designated Holdout, Prospective or production promotion.

## Global stage rule

At the start of every PR:

1. fetch default branch and exact latest main SHA;
2. search same-purpose paths, classes, branches, Issues and open/closed PRs;
3. re-audit neighboring PRs and ownership;
4. stop on duplicate implementation;
5. implement only the named stage;
6. run focused local checks after each meaningful change;
7. run full local gates once at the end;
8. push and open a Draft PR; do not merge or mark Ready.
