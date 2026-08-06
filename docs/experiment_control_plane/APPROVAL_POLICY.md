# Approval Policy

## 1. Principle

Approval is evidence bound to an immutable subject. A label, Project field, Issue comment, reaction,
assignee, or Check conclusion alone is not formal approval.

The approved subject is identified by:

```text
resource_type
resource_id
resource_sha256
policy_id
policy_sha256
scope
```

Any result-affecting change invalidates the approval and requires a new approval record.

## 2. Approval scopes

```text
PLAN_REVIEW
EXECUTION
PAID_API
HOLDOUT_OPEN
PROSPECTIVE_LOCK
RESULT_ACCEPTANCE
```

The following scopes are not owned by this subsystem:

```text
PROMOTION
REGISTRY
SHADOW_CANARY
PRIMARY
PRODUCTION_BINDING
```

Those remain under Promotion Governance PR #137 and later production authorities.

## 3. Approval evidence

A formal approval record contains:

```text
approval_id
resource_type
resource_id
resource_sha256
policy_id
policy_sha256
scope
decision
approver_login
approver_account_id
approver_role
approved_at_utc
expires_at_utc | null
supersedes_approval_id | null
revocation_reason_code | null
github_repository_id
github_commit_sha
evidence_sha256
```

The mutable display name of an approver is not an identity. Account ID and login are retained.
Raw OAuth, App, or Actions tokens are prohibited.

## 4. Separation of duties

For a single-user personal repository, GitHub cannot prove independent human separation. The system
must record:

```text
separation_of_duties=NOT_AVAILABLE_SINGLE_ACTOR
```

It must not pretend that self-approval is independent review. When multiple formal approvers are
required, migrate the governance surface to an organization or use an independently controlled
external approval authority.

## 5. Fail-closed rules

Approval is invalid when:

- the resource hash differs;
- the policy hash differs;
- the approval expired;
- the approval was revoked or superseded;
- the approver lacks the required role;
- the approval scope is wrong;
- the subject contains unresolved protected-stage requirements;
- the approval is synthetic, fixture, injected, or self-reported;
- only a label, comment, reaction, Project field, or Issue state exists.

## 6. Stage gates

| Gate | Required evidence |
|---|---|
| plan review | exact plan hash and policy hash |
| execution | plan approval, code/data/protocol identities, lane and budget |
| paid API | pricing snapshot, request/token/cost limits, secret boundary |
| Holdout open | explicit one-time approval and Data Access Ledger reference |
| Prospective lock | prediction bytes, hash, trusted-time reference and no Actual access |
| result acceptance | evaluation summary, all seeds, baselines and evidence index |

## 7. Non-claims

This policy does not generate human approval, configure GitHub Environments, change rulesets,
perform Promotion, mutate Registry state, or open Holdout/Prospective data.
