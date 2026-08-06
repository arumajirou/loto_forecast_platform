# Architecture — GitHub Webhook Receiver Foundation v1

## Component boundary

```text
GitHub HTTP POST
  -> isolated FastAPI router
  -> ReceiverService
     -> request limits and header parsing
     -> SecretRing HMAC verification
     -> duplicate-key-safe JSON parsing
     -> strict event normalizer
     -> WebhookStore transaction
        -> delivery
        -> status history
        -> dispatch-v1 outbox
  -> immediate 202/200/4xx/503 response

separate future worker
  -> claim outbox
  -> bounded handler execution
  -> success, retry, or dead letter
  -> future email/Project/workflow/MLflow adapters
```

## Request path

The request path has no SMTP, Slack, Project, MLflow, GitHub API, model, training, registry,
promotion, or prediction work. The durable outbox is the boundary that permits a response before
adapter execution while preserving recovery after restart.

## Authentication

`SecretRing` receives secret bytes through runtime dependency injection. It supports one active and
one previous key. Verification iterates the bounded ring and uses `hmac.compare_digest`. Only the
matching `key_id` is retained.

## Normalization

Raw payload models are intentionally not persisted. Extractors select required event fields and
construct strict normalized models. Repository identity is checked from both numeric ID and full
name. Action allowlists are event-specific.

## Persistence and concurrency

SQLite uses:

- `BEGIN IMMEDIATE` for delivery and outbox insertion;
- a primary key over repository and delivery identity;
- unique outbox identity over repository, delivery, and handler;
- WAL and a bounded busy timeout;
- one transaction for claim state transitions;
- an explicit processing lease recovery operation.

This lane is suitable for local and single-process verification. PostgreSQL remains the preferred
future multi-process production lane and requires its own migration, concurrency, failover, and
reconciliation evidence.

## Retry

The claim attempt is incremented atomically. Transient failures receive exponential delay with a
deterministic bounded jitter derived from delivery ID, handler, and attempt. Permanent failures and
attempt exhaustion become dead letters. No exception body is stored.

## HTTP adapter

`create_github_webhook_router(service)` creates:

```text
POST /webhooks/github
GET  /webhooks/github/health
```

It is not attached to the existing platform application in this PR. The health response exposes
only enablement, store readiness, queue depth, and explicit false values for raw-payload persistence
and adapters.

## Metrics

The foundation declares:

```text
github_webhook_requests_total{event,result}
github_webhook_signature_failures_total
github_webhook_duplicates_total{result}
github_webhook_ack_seconds{event,result}
github_webhook_queue_depth
github_webhook_dead_letters_total{handler}
```

Metrics are created against an injected Prometheus registry to avoid global-registration collisions
in tests and multi-app processes.

## Deployment boundary

Production registration requires a separate branch and review for HTTPS termination, callback URL,
secret manager, IP policy, process supervision, database selection, migrations, worker deployment,
metrics export, alerting, retention execution, backup/restore, and webhook registration evidence.
