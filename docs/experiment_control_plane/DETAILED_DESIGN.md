# Detailed Design

## 1. Plan identity

`experiment_plan_sha256` covers canonical plan content excluding only its self-hash. It includes:

- schema version and experiment ID;
- Issue reference;
- code commit and dirty-worktree policy;
- data snapshots and roles;
- model IDs, repositories, immutable revisions, artifact hashes;
- execution lane, device, concurrency, timeout, and fallback policy;
- seeds and aggregation;
- evaluation protocol and baseline inventory;
- HPO/search budget;
- API and GPU budget;
- protected-stage policy;
- required evidence inventory.

Changing any result-affecting field creates a new plan identity and invalidates prior approvals.

## 2. Approval identity

Approval covers:

```text
approval_id
plan_sha256
scope
approver
actor_kind
approved_at_utc
expires_at_utc | null
one_time
nonce
conditions[]
approval_sha256
```

The approver is not inferred from the PR author. A GitHub review may be referenced, but a mutable
comment alone is insufficient for formal approval.

## 3. Dispatch idempotency

`dispatch_key` is SHA-256 of:

```text
plan_sha256
scope
execution_lane
requested_stage
attempt_generation
```

It excludes request timestamp, GitHub workflow run ID, runner ID, PID, and trace ID.

Duplicate dispatch returns the existing Run ID. Conflicting payloads with a declared existing key
fail closed.

## 4. Execution lanes

### LOCAL_CPU

- no API secret;
- explicit CPU/thread inventory;
- maximum eight workers;
- deterministic thread policy.

### LOCAL_GPU

- one formal GPU process by default;
- GPU UUID/PID/VRAM/device evidence;
- no silent CPU fallback;
- local model snapshot and revision verification.

### API_PAID

- provider/model/endpoint identity;
- request, token, time, and cost caps;
- circuit breaker;
- request/response hashes;
- provider request IDs;
- credentials released only after authorization.

## 5. Heartbeat

A heartbeat includes:

```text
run_id
attempt
fencing_token
state
stage
progress_current
progress_total
last_completed_unit
resource_summary
cost_summary
created_at_utc
heartbeat_sha256
```

The GitHub projection is rate-limited. Detailed high-frequency samples stay in telemetry storage.

## 6. Check state mapping

| Platform state | Check status/conclusion |
|---|---|
| queued/running | queued/in_progress |
| awaiting approval | completed/action_required |
| external wait | completed/neutral |
| verified pass | completed/success |
| policy violation | completed/failure |
| cancelled | completed/cancelled |
| timeout | completed/timed_out |
| infrastructure unavailable | completed/neutral with explicit classification |

## 7. GitHub Project synchronization

Use stable field IDs discovered and stored by an audited export. Updates use compare-and-set
semantics where possible. Missing Project permission is `BLOCKED_PROJECT_PERMISSION`, not success.

## 8. Result PR

A Result PR adds:

```text
experiments/results/<experiment-id>/
  RESULT_SUMMARY.json
  EVALUATION_SUMMARY.json
  EVIDENCE_INDEX.json
  VERIFICATION_REPORT.md
  ARTIFACT_MANIFEST.json
  SHA256SUMS
```

It does not add weights, raw data, full Parquet, or full trace files.

## 9. Campaign release

A Release is allowed only after result review and campaign aggregation. The release notes bind
campaign manifest, included Run IDs, exact Git commit, and evidence bundle hash. A Release does not
promote or deploy a model.
