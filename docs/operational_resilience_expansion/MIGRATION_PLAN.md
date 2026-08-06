# Migration Plan

## 1. General policy

No bulk rewiring. Migrate one bounded workflow per PR and preserve the old path until parity is
demonstrated.

## 2. Durable lifecycle adoption

1. Implement pure foundation.
2. Add storage adapter.
3. Wrap one research workflow in shadow mode.
4. Compare old and new state/evidence.
5. Run duplicate/restart tests.
6. Make lifecycle authoritative only after parity.
7. Keep rollback switch for one release.

## 3. Clock health adoption

1. Run observation-only on target host.
2. Review thresholds over several days.
3. Emit warning without blocking.
4. Add Prediction Lock precondition in a separate PR.
5. Block only after false-positive review.
6. Trusted-time evidence remains separate.

## 4. Sandbox adoption

1. Implement policy and command builder.
2. Run a harmless fake provider.
3. Verify network, mounts, environment, limits.
4. Migrate one remote-code provider.
5. Compare runtime evidence with the current executor.
6. Do not remove provider-local protections until parity passes.

## 5. Database migration adoption

1. Inventory every current table and schema.
2. Do not stamp production as current.
3. Establish Alembic control for new `loto_ops` objects first.
4. Add outbox tables through a reviewed revision.
5. Validate backup and restore before first target upgrade.
6. Use expand/migrate/contract for incompatible changes.

## 6. Outbox adoption

1. Shadow-write outbox without external dispatch.
2. Verify message volume and hashes.
3. Enable one fake destination.
4. Enable one real non-critical destination.
5. Run reconciliation reports.
6. Move run completion gate to verified receipts.
7. Add remaining destinations one by one.

## 7. Rollback

- Foundation packages: stop importing or revert PR.
- Schema changes: use reviewed downgrade only when data-safe.
- Outbox: stop dispatcher; preserve messages and receipts.
- Clock gate: switch to observation-only through reviewed configuration.
- Sandbox: revert one provider adapter; retain evidence.
- Never delete evidence to make rollback appear successful.
