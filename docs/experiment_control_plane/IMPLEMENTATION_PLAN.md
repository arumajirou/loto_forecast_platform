# Implementation Plan

## PR-1 Experiment Plan Contract v1

Add strict, pure contracts and validators under a new bounded package. No GitHub API, workflow,
settings, dependency, or execution integration.

## PR-2 Experiment Intake Forms and Templates v1

Add Issue Form, plan/result PR templates, examples, and validation documentation. The Issue body is
not the formal contract.

## PR-3 Project Schema and Evidence Export v1

Create or configure Project fields/views only after capability and permission audit. Add idempotent
Project export/sync contracts. Project remains non-authoritative.

## PR-4 GitHub App and Check Run Contract v1

Define App permissions, installation-token handling, Check state mapping, deduplication, and fake
API tests. App registration/settings may require owner action.

## PR-5 Local Experiment Agent Foundation v1

Implement outbound-only queue polling, clean workspace, lane selection, heartbeat, cancellation,
evidence upload protocols, and fake executor tests. Integrate PR #140 lifecycle when available.

## PR-6 GitHub Control Workflows v1

Add short reusable workflows for plan validation, dispatch enqueue, result verification, and Project
sync. Do not add long-running model jobs. Start only after Issue #58 has actionable resolution.

## PR-7 Result PR and Evidence Index v1

Implement result summary/index contracts, remote verification adapters, and result PR generation.

## PR-8 Proprietary API Budget Lane v1

Implement pricing snapshot, budget reservation, token/request limits, cost reconciliation, circuit
breaker, and secret boundary.

## PR-9 Campaign Tags and Releases v1

Add protected naming rules, campaign manifest, release generator, and tag/ruleset owner runbook.
Release does not imply Promotion.

## PR-10 Target-host Integration and Failure Tests v1

Exercise GitHub App, local agent, evidence store, retry, cancellation, duplicate dispatch, GitHub
outage, agent restart, and reconciliation.

## Implementation rules

- Every PR starts from the then-current main.
- Documentation branch is read-only design input.
- One PR owns one bounded capability.
- Root dependency changes are isolated.
- GitHub settings changes are reported separately from repository code changes.
- Draft PRs remain unmerged until explicit approval.
