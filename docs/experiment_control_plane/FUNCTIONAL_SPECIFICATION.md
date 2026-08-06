# Functional Specification

## 1. Experiment lifecycle

```text
PROPOSED
→ PLAN_DRAFT
→ PLAN_REVIEW
→ PLAN_APPROVED
→ QUEUED
→ DISPATCHED
→ RUNNING
→ PREDICTION_LOCKED
→ WAITING_FOR_ACTUAL
→ ACTUAL_VERIFIED
→ EVALUATING
→ RESULT_REVIEW
→ COMPLETED
```

Alternate states:

```text
BLOCKED
CANCEL_REQUESTED
CANCELLED
TIMED_OUT
FAILED_RETRYABLE
FAILED_TERMINAL
RECONCILIATION_REQUIRED
REJECTED
```

Completion does not imply Promotion eligibility.

## 2. Formal objects

- `ExperimentPlan`
- `ExperimentPlanApproval`
- `DispatchRequest`
- `DispatchReceipt`
- `ExecutionHeartbeat`
- `ExecutionCompletion`
- `PredictionEvidenceReference`
- `ActualEvidenceReference`
- `EvaluationSummary`
- `EvidenceIndex`
- `ResultReview`
- `ProjectProjection`
- `BudgetLedger`

All objects are immutable evidence. Mutable GitHub Issues and Projects reference these objects.

## 3. Approval scopes

```text
PLAN_REVIEW
EXECUTION
PAID_API
HOLDOUT_OPEN
PROSPECTIVE_LOCK
RESULT_ACCEPTANCE
```

`PROMOTION`, `REGISTRY`, `SHADOW_CANARY`, and `PRIMARY` are explicitly excluded and remain under
Promotion Governance.

## 4. Dispatch

A valid dispatch requires:

1. exact plan SHA;
2. current plan approval;
3. exact code commit;
4. required data and protocol identities;
5. lane availability;
6. budget availability;
7. no active duplicate semantic dispatch;
8. protected-stage approvals;
9. GitHub App identity;
10. fail-closed result.

The control workflow creates a Run ID and queue record, then exits. It does not wait for training.

## 5. Local Experiment Agent

The agent:

- polls an authenticated queue or receives an already verified local work item;
- never exposes a public inbound endpoint;
- creates a clean execution workspace;
- re-verifies plan and Git identities;
- obtains secrets only for the selected lane;
- executes the existing platform command;
- publishes heartbeat and evidence references;
- supports cancellation and recovery;
- does not merge PRs or promote models.

## 6. Check Runs

Bounded Check inventory:

```text
experiment/plan-contract
experiment/approval
experiment/data-integrity
experiment/leakage-gate
experiment/runtime-certification
experiment/budget
experiment/prediction-lock
experiment/actual-source
experiment/evaluation
experiment/multi-seed
experiment/evidence-integrity
experiment/result-review
```

Allowed conclusions map conservatively to GitHub Checks. `neutral` or `action_required` is preferred
for pending human/external gates; formal success is used only when the represented gate passed.

## 7. Evidence index

The index contains no secret-bearing payload. It stores:

```text
artifact_type
artifact_id
uri
size_bytes
sha256
media_type
producer
created_at_utc
verification_status
source_system
retention_class
sensitivity
```

A URI with credentials or query tokens is invalid.

## 8. Project projection

Recommended status and fields:

```text
Status
Experiment ID
Run ID
Game
Execution Lane
Model ID
Protocol Hash
Data Snapshot
Prediction Lock
Actual Status
Primary Result
Verdict
API Cost
GPU Hours
Risk
Blocker
Next Gate
```

Project changes never authorize execution by themselves.

## 9. Run/Trial/Campaign hierarchy

```text
Trial      → MLflow / PostgreSQL
Run        → GitHub Checks + Result summary + Evidence index
Campaign   → reviewed tag and optional Release
Prospective window → prediction-lock bundle and reviewed Release
```
