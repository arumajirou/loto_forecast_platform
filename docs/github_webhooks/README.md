# GitHub Webhook Receiver Foundation v1

## Status

`PARTIALLY_VERIFIED / LOCAL_RECEIVER_EXECUTED / PUBLIC_CALLBACK_NOT_REGISTERED / ADAPTERS_DISABLED`

This package implements a disabled-by-default, repository-scoped GitHub webhook receiver foundation.
It validates the exact raw request body before JSON parsing, normalizes only approved event fields,
persists trusted metadata and a durable outbox in SQLite, and provides bounded retry and dead-letter
state transitions.

It does not register a GitHub webhook, expose a public callback, store a real secret, enable email,
Slack, Project, or MLflow adapters, or modify the existing platform API application.

## Provenance

- repository: `arumajirou/loto_forecast_platform`
- base: `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- branch: `agent/github-webhook-receiver-foundation-v1`
- design source: Draft PR #139 head
  `814b59d49944b234dafc9deba1cb07b230c9a348`
- Actions state: `ACTIONS_BLOCKED_PRE_RUN` under Issue #58

## Trust sequence

A delivery is accepted only after:

1. receiver enablement, body-size, and JSON content-type checks;
2. required GitHub header validation;
3. HMAC-SHA256 verification over the exact raw bytes;
4. UTF-8 and duplicate-key-safe JSON parsing;
5. exact repository ID and full-name allowlist validation;
6. event and action allowlist validation;
7. strict event-specific normalization;
8. atomic delivery, status-history, and outbox persistence.

No external network request occurs in the request path.

## Supported events

- `push`
- `pull_request`
- `issues`
- `workflow_run`

The exact allowed actions are configured in
`configs/github_webhooks/receiver_v1.yaml`. Unsupported event names and actions fail closed.

## Persistence

SQLite is the local-development and single-process evidence lane. The store contains:

- trusted delivery metadata and canonical normalized JSON;
- one durable outbox record per configured dispatch handler;
- append-style status history;
- dead-letter records after bounded retry exhaustion.

The raw payload, signature header, webhook secret, authorization headers, email addresses not needed
by the normalized model, Holdout values, Prospective values, model weights, and arbitrary
attachments are not persisted.

## Runtime activation boundary

The committed configuration uses `enabled: false`. A caller must inject a runtime `SecretRing` and
an explicit enabled policy. Secret bytes never appear in the YAML configuration, Pydantic models,
database schema, logs, metrics, smoke artifacts, or SHA inventory.

`create_github_webhook_router(service)` returns an isolated FastAPI router. This PR does not include
that router in `src/loto/api/app.py`.

## Commands

```bash
uv run python -m compileall -q \
  src/loto/github_webhooks \
  scripts/github_webhooks \
  tests/github_webhooks

uv run pytest -q tests/github_webhooks

uv run python scripts/github_webhooks/smoke_receiver.py \
  --policy configs/github_webhooks/receiver_v1.yaml \
  --output artifacts/github-webhook-smoke/<RUN_ID>
```

The smoke script uses an explicitly synthetic fixture key derived in memory and writes no signature,
secret, or raw body.

## Acceptance boundary

Local contracts and deterministic SQLite behavior can be verified before merge. Production
acceptance additionally requires HTTPS exposure, a secret manager, a real GitHub webhook
registration, target-host process and database evidence, restart and concurrency evidence,
bounded worker execution, observability, and an explicit deployment review.
