# Requirements

## 1. Goals

The system shall provide a fail-closed, auditable control plane for experiment planning, exact-subject approval, execution authorization, status projection, cancellation, result review and evidence discovery without making GitHub the durable experiment executor or evidence database.

## 2. Invariants

1. A mutable Issue, label, Project field, PR comment or branch name cannot by itself authorize execution.
2. Every approved action binds an immutable canonical subject SHA-256.
3. Changing code, config, data, protocol, model revision, seed set, budget, lane or gate invalidates prior approval.
4. Plan acceptance, execution authorization, Holdout opening, Prospective scoring, result acceptance and promotion are separate scopes.
5. No execution starts without a valid plan, policy pass, unexpired approval and idempotency key.
6. No Actual-dependent evaluation reads an Actual before the Prediction Lock and trusted-time gate permit it.
7. GitHub stores summaries and evidence references, not secrets, raw data, large artifacts or model weights.
8. Every side effect is idempotent, journaled and recoverable; retries do not duplicate a run or downstream commit.
9. A status projection cannot become more authoritative than its source evidence.
10. Failure, blocked and partially verified results are retained; they are never overwritten by a later successful run.

## 3. Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | Accept structured experiment intake and link it to an immutable Plan document. |
| FR-002 | Validate schema, canonical representation, identifier uniqueness and all required hashes. |
| FR-003 | Produce a deterministic `plan_sha256` and `approval_subject_sha256`. |
| FR-004 | Record append-only approvals with actor, scope, subject, expiry, reason and revocation state. |
| FR-005 | Reject self-approval when policy requires separation of duties; support a single-owner fallback with explicit reduced-assurance evidence. |
| FR-006 | Enqueue a run only after authorization, producing a deterministic request ID and unique Run ID. |
| FR-007 | Acquire/renew/release a fenced execution lease and reject stale workers. |
| FR-008 | Receive heartbeat, progress, cancellation and terminal result events without exposing the local host inbound. |
| FR-009 | Index external evidence by content hash, role, media type, size, producer, storage URI and verification result. |
| FR-010 | Verify result manifests, Prediction Lock references, evaluation summaries and baseline/multi-seed evidence before review. |
| FR-011 | Project canonical state into GitHub Checks, PR/Issue comments and the existing governance Project. |
| FR-012 | Support local GPU, local CPU and paid API lanes with distinct authorization and secret boundaries. |
| FR-013 | Maintain a complete audit trail for every requested, approved, rejected, revoked, queued, cancelled and completed action. |
| FR-014 | Export deterministic JSON reports and an evidence bundle index suitable for independent verification. |
| FR-015 | Integrate with promotion only through an immutable candidate/evidence handoff; never auto-promote. |

## 4. Evaluation requirements

Every formal forecasting result shall preserve:

```text
Primary: Hit@±1
Secondary: MAE, MSE, RMSE
Position-level Hit@±1
All-position Hit@±1
Random, fixed, mean, median, last-value, frequency and statistical baselines
Time-ordered Train / Validation / Holdout / Prospective boundaries
Train-only fitting of scalers, encoders, feature selection and HPO
OOF evidence
multiple seeds with mean, variance and worst value
prediction fixed before Actual with SHA-256 and trusted time
```

The control plane consumes the canonical evaluation protocol and report from its owner; it does not recompute or redefine these metrics.

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-001 | Strict Pydantic v2 models with `extra="forbid"` for all external contracts. |
| NFR-002 | Canonical JSON hashing with documented normalization and duplicate-key rejection. |
| NFR-003 | Append-only audit/event storage with tamper-evident chain or equivalent integrity evidence. |
| NFR-004 | Idempotent commands, bounded retries, exponential backoff and explicit timeout values. |
| NFR-005 | No secret values in logs, plans, manifests, GitHub comments or error payloads. |
| NFR-006 | Structured JSON logs with Run ID, request ID, actor, action, outcome and correlation/trace ID. |
| NFR-007 | OpenTelemetry-compatible metrics/traces through the repository's canonical telemetry contract when available. |
| NFR-008 | Atomic local writes, durable database transactions and verified object-store writes. |
| NFR-009 | Clock access injected; security decisions require trusted-time evidence where applicable. |
| NFR-010 | Linux and Windows operator commands; long-running local execution survives terminal closure. |
| NFR-011 | Focused local tests during development; full repository gates and GitHub CI only after implementation completion. |
| NFR-012 | No direct main write, force push, merge, Ready transition, release or production mutation without explicit owner approval. |

## 6. Acceptance criteria

The foundation is accepted only when:

1. invalid or changed plans fail closed;
2. an unapproved, expired, revoked or wrong-scope request cannot enqueue;
3. repeated identical enqueue returns the same command result without a duplicate run;
4. conflicting idempotency keys fail closed;
5. a stale worker cannot heartbeat, complete or publish evidence after lease takeover;
6. evidence hash mismatch prevents result acceptance;
7. Project/Check synchronization failure does not corrupt canonical state and is retryable;
8. a full local reference flow reaches result review using synthetic data without Holdout/Prospective/production mutation;
9. security scans find no credentials or private keys;
10. manifest and `SHA256SUMS` verify remotely after push;
11. GitHub Actions outcome is classified separately from code quality, including Issue #58 zero-step behavior;
12. every non-claim and unavailable verification remains explicit in the PR description.
