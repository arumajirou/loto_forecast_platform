# Detailed Design

## Canonical identity

```text
plan_sha256 = SHA256(canonical_json(plan_without_plan_sha256))
approval_subject_sha256 = SHA256(canonical_json({scope, plan_sha256, requested_action, constraints}))
execution_request_sha256 = SHA256(canonical_json(request_without_derived_fields))
evidence_index_sha256 = SHA256(canonical_json(index_without_index_sha256))
```

The implementation must use one canonicalization module. Re-serializing with arbitrary YAML/JSON libraries is not accepted as identity proof.

## Approval decision algorithm

```text
1. Load accepted Plan by immutable repository commit/path.
2. Recompute and compare plan SHA-256.
3. Build ApprovalSubject for requested scope.
4. Load all approval/revocation events for subject.
5. Reject unknown actor, insufficient role, self-approval policy violation,
   expired approval, revocation, wrong scope, wrong subject or ambiguity.
6. Evaluate lane, budget, data and external-evidence policies.
7. Return an immutable AuthorizationDecision with reasons and policy version.
```

The decision records both positive and negative evidence. Absence of a denial is not approval.

## Enqueue algorithm

```text
BEGIN TRANSACTION
  validate authorization decision revision
  lookup idempotency key
  if same key + same payload: return stored receipt
  if same key + different payload: fail IDEMPOTENCY_CONFLICT
  allocate Run ID
  append command and lifecycle event
  append projection outbox entries
COMMIT
```

No GitHub/API/object-store call occurs inside the canonical transaction. External effects are driven by an outbox.

## Lease and fencing

A lease contains:

```text
run_id
lease_id
worker_id
fence_token (strictly increasing)
acquired_at
expires_at
last_heartbeat_at
expected_run_revision
```

Every agent mutation carries `lease_id` and `fence_token`. After takeover, a stale worker cannot heartbeat, cancel, upload final evidence or complete the run.

## Agent execution loop

```text
Observe -> validate local capacity and policy
Acquire -> leased command with fence
Prepare -> isolated workspace and immutable inputs
Diagnose -> runtime/data preflight
Execute -> durable subprocess in tmux/systemd-user
Measure -> metrics, logs, resource telemetry, heartbeat
Seal -> prediction/result hashes before downstream access
Upload -> content-addressed evidence
Report -> terminal event and immutable receipt
Cleanup -> release secrets, processes, VRAM and workspace by retention policy
```

## Lane controls

### Local GPU

Required evidence includes model ID/revision, weight hash, runtime/engine revision, context/input shape, CUDA/driver/device/PID, VRAM peak, CPU fallback flag, finite output and load/infer/unload results.

### Local CPU

Required evidence includes host profile, thread/process limits, memory peak, runtime identity and deterministic/repeatability evidence where applicable.

### Paid API

Required evidence includes provider/model/snapshot, SDK version, request/response digests, provider request ID, tokens, latency, retries, rate-limit observations and bounded cost. Raw sensitive request/response content is not placed in GitHub.

## Cancellation

1. Persist cancellation request and reason.
2. Projection indicates cancellation requested, not completed.
3. Agent acknowledges and performs lane-specific cooperative stop.
4. After grace timeout, bounded escalation may terminate the process tree.
5. Seal partial logs/evidence and report `CANCELLED` or `FAILED_CANCELLATION` according to canonical lifecycle.
6. Never delete prior evidence as part of cancellation.

## Evidence verification

```text
HEAD/stat object -> validate size/media constraints
stream bytes -> SHA-256
verify optional signature/receipt
verify producer identity and subject binding
record verifier version + time + outcome
```

A URI that cannot be fetched is `UNAVAILABLE`, not `VERIFIED`. A digest mismatch is terminal for that evidence revision.

## GitHub synchronization

Projection events carry a deterministic key:

```text
projection_key = SHA256(target + source_event_id + projection_schema_version)
```

Repeated processing is idempotent. Project/Check updates never write back a more advanced canonical lifecycle state.

## Concurrency

- database row/revision checks protect commands and approvals;
- unique constraints protect idempotency keys and Run IDs;
- leases protect execution ownership;
- content-addressed object names protect evidence deduplication;
- outbox and projection keys protect external side effects;
- no global filesystem lock is considered sufficient for multi-process production use.
