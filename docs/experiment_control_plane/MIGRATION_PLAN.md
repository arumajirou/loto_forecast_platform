# Migration Plan

## Strategy

Use additive, shadow-first migration. Existing research commands, registries, MLflow integrations and model providers remain authoritative until a separately approved cutover.

## Steps

1. **Inventory** existing Plan/config/run/result identifiers and storage locations.
2. **Introduce contracts** without changing existing execution paths.
3. **Dual-write projections only**: produce control-plane summaries from existing completed runs; do not change execution authority.
4. **Import evidence references** by hashing existing immutable artifacts; mark unavailable/unverified bytes honestly.
5. **Shadow authorization**: evaluate whether commands would be allowed while legacy execution remains active.
6. **Controlled opt-in**: enable one synthetic/local CPU lane for explicit experiment IDs.
7. **Durability certification**: PostgreSQL/object-store/MLflow restart and idempotency tests.
8. **GitHub projection activation**: enable App Checks/Project sync after reconciliation tests.
9. **Lane expansion**: local GPU, then paid API after separate security and budget approval.
10. **Legacy retirement**: only after parity, rollback and audit evidence; retain read-only compatibility adapters for defined period.

## Compatibility rules

- Legacy run IDs are mapped, not rewritten.
- Missing protocol/data/model identities produce `UNVERIFIED_LEGACY`, not fabricated hashes.
- Existing MLflow runs are linked through deterministic tags only when identity can be proven.
- Existing GitHub Issues/PRs are conversation/evidence links, not reconstructed approval events.
- Promotion and production statuses are never inferred from a historical leaderboard.

## Rollback

Each PR is independently revertible. Runtime rollout uses feature flags and allowlisted experiment IDs. Rollback order:

```text
disable new enqueue
allow active runs to complete or cancel by policy
stop projection worker
export canonical DB/outbox/evidence index
revert routing to legacy executor
disable agent service and revoke App credentials
verify no production binding changed
retain audit/evidence read-only
```

No rollback deletes raw evidence or rewrites audit history.
