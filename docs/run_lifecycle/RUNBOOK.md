# Runbook

## Inspect a Run

1. Load the ordered event list.
2. Run `validate_lifecycle(events)`.
3. Stop on any `ERROR` finding.
4. Reconstruct with `replay_events(events)`.
5. Compare reconstructed revision and chain head with stored aggregate.
6. Inspect idempotency record count and duplicate observations.
7. Inspect active lease expiry and latest fencing token.

## Recover after process restart

1. Do not create a new Run ID.
2. Validate the complete prior event chain.
3. Replay the aggregate.
4. Acquire a new lease only after the prior lease has expired or been explicitly released by a
   future durable adapter.
5. Use the new fencing token.
6. Submit `RESUME` only from a matrix-supported recoverable state.
7. Declare requested output names so already sealed output is preserved instead of regenerated.

## Incident classifications

| Symptom | Classification | Action |
|---|---|---|
| event hash mismatch | `FAILED / EVIDENCE_TAMPER_OR_CORRUPTION` | stop writes; preserve bytes |
| revision mismatch | `BLOCKED / CONCURRENT_MUTATION` | reload aggregate and review |
| stale fencing token | `BLOCKED / STALE_WORKER` | stop old worker |
| idempotency conflict | `FAILED / KEY_PAYLOAD_CONFLICT` | investigate caller identity |
| expired lease heartbeat | `BLOCKED / EXPIRED_OWNER` | acquire takeover lease |
| terminal resume attempt | `BLOCKED / TERMINAL_IMMUTABILITY` | create a separately authorized new Run |
