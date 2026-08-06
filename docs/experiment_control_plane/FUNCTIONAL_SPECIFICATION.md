# Functional Specification

## Actors

| Actor | Authority |
|---|---|
| Requester | Propose an experiment and open a Plan PR; cannot authorize execution by proposal alone. |
| Reviewer | Review plan/evidence; may approve only scopes allowed by policy. |
| Controller service | Validate contracts, persist commands/events, issue leases and project state. |
| Local agent | Poll outbound, acquire a lease, execute an approved request, upload evidence and heartbeat. |
| GitHub App | Project canonical state into Checks/comments/Project fields using short-lived tokens. |
| Evaluation service | Produce canonical evaluation evidence under the repository's evaluation protocol. |
| Evidence verifier | Re-hash objects, validate signatures/receipts and update verification records. |
| Promotion governance | Consume an approved immutable candidate handoff; never infer approval from ranking. |

## Primary use cases

### UC-01 Propose an experiment

1. Requester opens an Issue Form for discussion and traceability.
2. Requester creates `experiments/plans/<experiment_id>.yaml` in a Plan PR.
3. Validator resolves exact code/config/data/protocol/model identities.
4. Validator emits deterministic hashes and a validation report.
5. Reviewers accept or reject the Plan PR.

Issue metadata is non-authoritative. The Plan document and its merged commit identity are authoritative for plan acceptance.

### UC-02 Authorize execution

1. Controller constructs an `ApprovalSubject` from the accepted plan and requested scope.
2. Reviewer records an `EXECUTE` ApprovalRecord for that exact subject.
3. A manual dispatch/API command supplies the plan hash and idempotency key.
4. Controller re-validates policy, approval, expiry and current plan identity.
5. Controller creates one ExecutionRequest and one Run ID, then returns immediately.

### UC-03 Execute through a local agent

1. Agent authenticates outbound and polls for eligible work.
2. Controller grants a fenced lease with bounded duration.
3. Agent verifies plan/evidence hashes locally before any expensive work.
4. Agent starts execution through `tmux` or a `systemd --user` service and writes durable local logs.
5. Agent reports heartbeat and metrics; Controller stores events and updates projections.
6. Cancellation is cooperative first, then bounded escalation; the reason is recorded.

### UC-04 Lock predictions and wait for Actual

1. Prediction artifact is produced and hashed before Actual access.
2. Trusted-time/Prediction Lock owner returns immutable evidence.
3. Run transitions to a waiting projection.
4. Actual source owner later provides verified Actual evidence.
5. Evaluation is authorized under a separate scope when required.

### UC-05 Review results

1. Agent/evaluator submits `result_summary.json` and `evidence_index.json` references.
2. Evidence verifier checks bytes, hashes, signatures, sizes and declared roles.
3. Evaluation report is validated against protocol/data/model/run identities.
4. Result PR contains only summaries, manifests and references.
5. Reviewer accepts, rejects or requests more evidence.
6. Promotion receives a separate immutable handoff only after explicit promotion governance.

## Command surface proposed for implementation

```text
loto3 experiment plan validate --plan <path>
loto3 experiment plan hash --plan <path>
loto3 experiment approval propose --plan <path> --scope EXECUTE
loto3 experiment approval record --subject <sha256> --scope EXECUTE --expires-at <time>
loto3 experiment approval revoke --approval-id <id> --reason <text>
loto3 experiment run enqueue --plan <path> --idempotency-key <key>
loto3 experiment run status --run-id <id>
loto3 experiment run cancel --run-id <id> --reason <text>
loto3 experiment evidence verify --index <path>
loto3 experiment result verify --summary <path> --index <path>
loto3 experiment export --run-id <id> --output <dir>
```

Commands that can mutate state must support `--dry-run`, emit machine-readable JSON, and never print secrets.

## GitHub projections

Recommended Check names:

```text
experiment/plan-contract
experiment/authorization
experiment/data-integrity
experiment/leakage-gate
experiment/runtime-certification
experiment/prediction-lock
experiment/baseline-comparison
experiment/multi-seed
experiment/evaluation
experiment/budget
experiment/evidence-integrity
experiment/prospective-gate
```

A Check result is a projection with a source event/version. It must never be accepted as the only evidence of the underlying control.

## Error taxonomy

| Code | Meaning | Retry |
|---|---|---|
| `PLAN_INVALID` | Schema or semantic validation failed | no until plan changes |
| `SUBJECT_MISMATCH` | Approval subject differs from requested action | no |
| `APPROVAL_MISSING` | No valid approval for scope | after approval |
| `APPROVAL_EXPIRED` | Approval time window ended | after new approval |
| `APPROVAL_REVOKED` | Approval explicitly revoked | after new approval |
| `IDEMPOTENCY_CONFLICT` | Same key used with different payload | no; operator review |
| `LEASE_CONFLICT` | Active lease held by another worker | retry with backoff |
| `STALE_FENCE` | Worker fence is older than canonical fence | no |
| `EVIDENCE_HASH_MISMATCH` | Referenced bytes do not match digest | no until evidence repaired |
| `STORAGE_UNAVAILABLE` | External evidence store unavailable | bounded retry |
| `PROJECTION_FAILED` | GitHub sync failed; canonical state intact | retry |
| `CI_BLOCKED_PRE_RUN` | Actions job created no workflow steps | no blind rerun; owner settings review |
| `POLICY_DENIED` | Requested lane/scope violates policy | no until policy/plan changes |
