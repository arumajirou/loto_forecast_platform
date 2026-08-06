# Requirements — GitHub Webhook Receiver Foundation v1

## Functional requirements

### WH-FR-001 — Raw-body authentication

The receiver must compute HMAC-SHA256 over the exact request bytes and compare the resulting
`sha256=` value through a constant-time comparison API before JSON parsing.

### WH-FR-002 — Secret rotation

The runtime may accept one active and one previous key during a bounded rotation window. Durable
records retain only the matching key ID, never key material.

### WH-FR-003 — Request boundary

The receiver must enforce a bounded body size, JSON content type, required delivery/event/signature
headers, UUID-compatible delivery identity, and exact supported event inventory.

### WH-FR-004 — Repository and action allowlists

Both numeric repository ID and exact `owner/name` must match the configured repository. Event
actions must be explicitly allowed. Unknown events, actions, repositories, and normalized fields
fail closed.

### WH-FR-005 — Durable idempotency

The unique key is `(repository_id, delivery_id)`. A duplicate with the same payload SHA-256 returns
an idempotent success without another outbox record. Reuse with a different hash is a conflict.

### WH-FR-006 — Data minimization

Raw payloads and secrets are not durable fields. Only strict normalized event metadata, payload
SHA-256, correlation identity, key ID, status, retry state, and masked error codes may be stored.

### WH-FR-007 — Transactional outbox

A new trusted delivery and its configured outbox rows must be inserted in one SQLite transaction.
The request path performs no adapter or external network call.

### WH-FR-008 — Retry and dead letter

Transient failures use bounded exponential backoff with deterministic jitter. Permanent failures or
retry exhaustion create a dead-letter record. Errors are bounded codes, not exception strings.

### WH-FR-009 — Restart recovery

Expired processing leases may be returned to retry without deleting the original delivery,
normalized event, attempt count, or audit history.

### WH-FR-010 — HTTP contract

A new trusted delivery returns 202, an identical duplicate returns 200, and a changed-hash replay
returns 409. Authentication and validation failures return 4xx, and unavailable durable storage
returns 503.

### WH-FR-011 — Observability

Metrics use bounded event/result/handler values only. Repository name, sender, delivery ID, commit
SHA, branch, Run ID, and free-form errors are prohibited labels.

### WH-FR-012 — Disabled default

The committed policy remains disabled. This PR must not register a public callback, enable adapters,
or add real credentials.

## Non-functional requirements

- Python 3.11–3.13 compatibility.
- Strict Pydantic v2 contracts with unknown-key rejection.
- SQLite standard-library implementation with atomic transactions.
- No root dependency or `uv.lock` change.
- Deterministic canonical JSON and SHA-256 evidence.
- Source and test lines at or below the repository's 100-character limit.
- No mutation of Registry, Promotion, Approval, Canary, Production, evaluation, Prediction Lock,
  Holdout, Prospective, or raw data.

## Acceptance criteria

The foundation is locally accepted when focused tests prove authentication ordering, strict
normalization, idempotency, conflict rejection, concurrency, retry, dead letter, restart recovery,
HTTP status behavior, secret non-persistence, and bounded metrics.

The receiver is not production-certified until a separately approved deployment supplies HTTPS,
secret storage, a durable multi-process database lane where required, real GitHub delivery evidence,
worker runtime evidence, and rollback verification.
