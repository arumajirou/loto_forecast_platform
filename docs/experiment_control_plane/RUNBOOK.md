# Runbook

## Before implementation

1. Fetch repository metadata and latest main SHA.
2. Re-read the design PR and verify all design hashes.
3. Search branches, open/closed PRs, Issues, and code paths.
4. Inspect PR #121, #123–#141 and newer cross-cutting work.
5. Confirm current Actions Issue #58 state.
6. Confirm current account plan, repository ownership, Ruleset, Environment, Project, App, and
   self-hosted-runner capabilities.
7. Stop on ownership conflict.

## Before dispatch

```text
PLAN_VERIFIED
APPROVAL_VERIFIED
CODE_SHA_VERIFIED
DATA_SHA_VERIFIED
PROTOCOL_HASH_VERIFIED
BUDGET_RESERVED
LANE_AVAILABLE
DUPLICATE_NOT_ACTIVE
PROTECTED_STAGE_AUTHORIZED
```

## During run

- monitor durable Run state, not only GitHub Check;
- keep Check/Project updates rate-limited;
- retain heartbeat and cost;
- cancel on policy violation;
- do not expose API credentials to local model code.

## Completion

- verify required artifacts and hashes;
- verify prediction lock chronology;
- verify Actual provenance if scoring;
- verify evaluation metrics and all seeds;
- publish Result PR and Check summary;
- reconcile GitHub projection with evidence store.

## Incident classifications

```text
GITHUB_UNAVAILABLE
ACTIONS_BLOCKED_PRE_RUN
PROJECT_PERMISSION_BLOCKED
APP_TOKEN_FAILURE
LOCAL_AGENT_UNAVAILABLE
STALE_AGENT_REJECTED
BUDGET_EXCEEDED
EVIDENCE_STORE_UNAVAILABLE
EVIDENCE_HASH_CONFLICT
PREDICTION_LOCK_INVALID
ACTUAL_SOURCE_INVALID
```
