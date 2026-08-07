# Runbook — GitHub Webhook Receiver Foundation v1

## Pre-activation checks

1. Confirm the implementation branch starts from the recorded current `main`.
2. Confirm all changes remain within the webhook-owned path allowlist.
3. Confirm root dependencies, `uv.lock`, existing API app, workflows, models, Registry, and
   evaluation paths are unchanged.
4. Run compileall, focused pytest, Ruff, mypy, secret scan, and SHA verification.
5. Run the signed local smoke into a new output directory.
6. Confirm configuration remains `enabled: false`.
7. Confirm no real callback URL, signature, token, SMTP credential, or secret value is committed.

## Local smoke interpretation

A valid smoke proves only:

- the fixture signature is accepted;
- the normalized issue event is persisted;
- the duplicate is idempotent;
- one outbox record exists;
- evidence artifacts contain no fixture secret or signature.

It does not prove GitHub connectivity, HTTPS, target-host durability, or adapter execution.

## Future activation sequence

1. Resolve Issue #58 or classify it separately without feature-code workarounds.
2. Select a target host and HTTPS termination strategy.
3. Store a high-entropy secret in an approved secret manager.
4. Select SQLite only for a reviewed single-process lane; otherwise implement PostgreSQL.
5. Deploy receiver and worker processes with separate identities and bounded permissions.
6. Verify health, metrics, structured logs, restart recovery, and backup/restore.
7. Register the repository webhook for only approved events.
8. Send one signed ping or supported event and retain GitHub delivery evidence.
9. Verify acknowledgement below 10 seconds and durable outbox creation.
10. Test duplicate redelivery, invalid signature, changed-hash replay, store failure, retry, and
    dead-letter alerting.
11. Enable adapters only in their separate approved increment.

## Secret rotation

1. Add the new key as active and retain the previous key temporarily.
2. Update the GitHub webhook secret.
3. Verify deliveries match the new key ID.
4. After the bounded overlap window, remove the previous key.
5. Never log or export either secret or signature.

## Incident procedures

### Invalid-signature surge

- do not persist the payload as trusted;
- inspect bounded counters and source-network controls;
- verify proxy body preservation and secret version;
- rotate only through the approved secret procedure;
- never copy signatures or raw payloads into public Issues.

### Delivery hash conflict

- treat as a security event;
- retain delivery ID, repository ID, both known hashes, trace ID, and bounded timestamps;
- do not replace the original normalized record;
- inspect GitHub delivery history and secret integrity.

### Store unavailable

- return 503 and do not acknowledge durable acceptance;
- restore the store before redelivery;
- remember that GitHub does not automatically redeliver failed deliveries;
- use a separately reviewed manual or scheduled redelivery procedure.

### Worker crash

- preserve the delivery and outbox;
- recover expired processing leases to retry;
- reconcile external side effects before retry;
- never infer side-effect failure from a missing local completion receipt.

### Dead letter

- inspect the bounded error code and normalized metadata;
- correct the handler or configuration;
- reprocess through a new governed processing attempt;
- retain original delivery identity and audit history.

## Rollback

Before merge, close the Draft PR. After merge but before activation, revert the add-only package.

After deployment:

1. disable the GitHub webhook;
2. drain or preserve the outbox;
3. export normalized delivery, history, and dead-letter evidence;
4. stop worker and receiver;
5. restore the previous deployment;
6. verify no adapter side effect is repeated;
7. remove the callback only after evidence retention is complete.
