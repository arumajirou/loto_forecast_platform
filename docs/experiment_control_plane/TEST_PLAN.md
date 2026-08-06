# Test Plan

## Test levels

### Contract tests

- unknown fields, invalid enum, malformed SHA/timestamp/URI;
- duplicate semantic keys;
- canonical hash stability across supported serialization inputs;
- any identity mutation changes the subject hash;
- invalid split order, duplicate seeds, missing baselines and unpinned revisions fail.

### Approval tests

- missing/wrong-scope/expired/revoked approval denied;
- self-approval policy enforced;
- exact subject and policy version required;
- one-time use consumed atomically;
- revocation racing enqueue has one deterministic outcome;
- history tampering detected.

### Idempotency and lifecycle tests

- repeated same command returns same receipt;
- same key/different payload conflicts;
- concurrent enqueue creates one Run ID;
- stale expected revision fails;
- lease expiry/takeover increments fence;
- stale worker mutations fail;
- restart replay preserves terminal/sealed evidence.

### Evidence tests

- hash, size, media type and subject verification;
- missing object, permission denial and transient outage classifications;
- credentials/query secrets rejected in URI;
- corrupted object prevents result acceptance;
- retention deletion creates tombstone and keeps audit metadata.

### Projection tests

- outbox replay is idempotent;
- Check/Project API outage does not rollback canonical transaction;
- stale projection cannot regress or advance canonical state;
- reconciliation repairs missing projections;
- token values and sensitive evidence never appear in requests/logs beyond allowed fields.

### Agent tests

- workspace traversal rejection;
- process-tree cancellation;
- heartbeat timeout and lease loss;
- terminal closed window recovery through tmux/systemd-user logs;
- resource limit enforcement;
- local GPU rejects CPU fallback/non-finite output and verifies VRAM release;
- paid API enforces request/token/cost limits and circuit breaker.

### Forecast governance integration

- Train-only fit and time ordering evidence reference present;
- Hit@±1 primary and required secondary metrics/baselines present;
- multi-seed mean/variance/worst present;
- Prediction Lock precedes Actual access;
- no automatic promotion from first place or best seed.

## Development gate order

```text
Ruff format/check on owned paths
mypy on owned paths
focused pytest
smoke execution
secret scan
artifact size scan
manifest/SHA verification
then once: full pytest + coverage + dependency/security audit + GitHub CI
```

GitHub CI is classified separately. A run with no workflow steps and unavailable logs is `CI_BLOCKED_PRE_RUN`, not a test failure.

## Operational certification scenarios

1. normal synthetic local CPU campaign;
2. controller restart during running state;
3. agent crash and lease takeover;
4. object store unavailable then recovery;
5. evidence byte corruption;
6. GitHub projection outage then reconciliation;
7. approval revoked before lease;
8. approval revoked during run under each policy option;
9. cancellation and process-tree cleanup;
10. backup restore and audit-chain verification.

## Required artifacts

```text
test-results.json
coverage.xml
verification-report.json
secret-scan.json
runtime-evidence.json
evidence-index.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```
