# Experiment Control, Approval, and Evidence Index Foundation v1

## Status

```text
DOCUMENTATION_STATUS=EXECUTED
DESIGN_STATUS=PARTIALLY_VERIFIED
IMPLEMENTATION_STATUS=EXECUTION_PENDING
PRODUCTION_MUTATION=false
LIVE_GITHUB_CONFIGURATION_CHANGED=false
BASE_MAIN_SHA=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
FACT_CHECKED_AT=2026-08-06T18:22:00+09:00
```

## Purpose

This package defines the implementation-ready foundation that connects three deliberately separate planes:

```text
GitHub control plane
  plans, explicit approvals, desired state, checks, review, audit index

Local/API execution plane
  training, inference, HPO, evaluation, retries, heartbeat, cancellation

Evidence plane
  PostgreSQL, MLflow, Parquet, object storage, logs, metrics, traces, models
```

GitHub is not the durable executor or the primary evidence store. It retains small, reviewable contracts and content-addressed references:

```text
Experiment ID / Run ID
code, config, data, protocol and model identities
approval scope and exact approved subject hash
prediction/evidence hashes
result summary and verdict
external evidence URIs without credentials
```

## Non-goals

This documentation PR does not:

- start experiments, open Holdout or Prospective data, or score an unpublished Actual;
- create a live GitHub Project, GitHub App, Environment, ruleset, runner, webhook, workflow, release or deployment;
- alter Registry, PlatformRegistry, Promotion, Prediction Lock, Actual Source or production binding;
- place secrets, raw datasets, model weights or large experiment artifacts in GitHub;
- merge, mark Ready, auto-merge, or modify `main`.

## Document map

| Document | Purpose |
|---|---|
| `FACT_CHECK_REPORT.md` | Repository and official GitHub capability audit |
| `REQUIREMENTS.md` | Goals, constraints and acceptance criteria |
| `FUNCTIONAL_SPECIFICATION.md` | Use cases, commands, gates and behavior |
| `ARCHITECTURE.md` | Plane separation, trust boundaries and data flows |
| `BASIC_DESIGN.md` | Components, ownership boundaries and package map |
| `DETAILED_DESIGN.md` | State handling, idempotency, leases and algorithms |
| `DATA_CONTRACT.md` | Canonical plan/request/result contract examples |
| `APPROVAL_MODEL.md` | Approval scopes, exact-subject binding and revocation |
| `EVIDENCE_INDEX_CONTRACT.md` | Evidence reference and verification contract |
| `SOURCE_REGISTRY.md` | Primary official sources used by this design |
| `IMPLEMENTATION_PLAN.md` | Independent Draft PR sequence and dependencies |
| `IMPLEMENTATION_SCHEDULE.md` | Phase gates and exit criteria |
| `TEST_PLAN.md` | Local, integration, security and operational tests |
| `MIGRATION_PLAN.md` | Additive rollout, compatibility and rollback |
| `RISK_REGISTER.md` | Risks, controls, owners and evidence |
| `TRACEABILITY_MATRIX.md` | Requirement-to-test-to-artifact mapping |
| `RUNBOOK.md` | Operator procedures and failure classification |
| `VERIFICATION_REPORT.md` | What was and was not verified in this docs PR |
| `HANDOFF.md` | Owner and implementer handoff checklist |
| `IMPLEMENTATION_PROMPT.md` | Authoritative push-oriented implementation prompt |
| `prompts/*.md` | Stage-specific implementation prompts |
| `IMPLEMENTATION_BACKLOG.yaml` | Machine-readable staged backlog |
| `ARTIFACT_MANIFEST.json` | Managed artifact inventory |
| `SHA256SUMS` | Byte-level integrity list |

## Authoritative implementation rule

Every implementation stage must start from the then-current `main`, repeat duplicate and ownership audits, and stop rather than copy a capability that has already landed. Open Draft PRs are design references only until merged. The first implementation stage must not branch from this documentation branch.

## Recommended first implementation

```text
PR-1 Experiment Plan Contract v1
branch: feat/experiment-plan-contract-v1
scope: strict contracts, canonical hashing, validators, examples, focused tests
side effects: none
```

The complete push-oriented prompt is in `IMPLEMENTATION_PROMPT.md`.
