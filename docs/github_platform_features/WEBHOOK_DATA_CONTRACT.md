# Webhook Data Contract — GitHub Platform Features Foundation v1

## 1. Purpose

Define the normalized, persistence, privacy, and compatibility contract for GitHub webhook deliveries. Raw payloads are transport inputs, not durable domain records.

## 2. Trust boundary

A delivery becomes trusted only after:

1. HTTPS termination is valid;
2. body size and content type pass;
3. required headers are present and syntactically valid;
4. HMAC-SHA256 over the exact raw body passes constant-time comparison;
5. repository ID/full name is allowlisted;
6. event type and action are supported;
7. normalized schema validation passes;
8. the event is durably persisted or atomically placed in an outbox.

JSON parsing, handler routing, email, Project access, and MLflow access never substitute for signature verification.

## 3. Header contract

| Header | Required | Validation |
|---|---|---|
| `X-GitHub-Event` | yes | allowlisted lowercase event name |
| `X-GitHub-Delivery` | yes | UUID-compatible unique delivery identifier |
| `X-Hub-Signature-256` | yes | `sha256=` plus 64 lowercase/normalized hex characters |
| `Content-Type` | yes | `application/json` with optional charset |
| `X-GitHub-Hook-ID` | optional | positive integer; metadata only |
| `User-Agent` | optional | bounded string; not trusted identity |

## 4. Normalized envelope

| Field | Type | Required | Rules |
|---|---|---|---|
| `schema_version` | string | yes | fixed semantic version, initially `1.0.0` |
| `delivery_id` | UUID | yes | combined with repository ID for uniqueness |
| `event_type` | enum | yes | push/pull_request/issues/workflow_run initially |
| `action` | string/null | yes | bounded event-specific value |
| `repository_id` | int | yes | positive and allowlisted |
| `repository_full_name` | string | yes | exact expected owner/name |
| `sender_login` | string/null | no | validated/bounded; excluded from metrics labels |
| `ref` | string/null | no | bounded Git ref |
| `head_sha` | string/null | no | 40/64 hex according to supported Git identity policy |
| `payload_sha256` | string | yes | SHA-256 of exact raw body |
| `received_at` | aware datetime | yes | UTC |
| `signature_verified` | bool | yes | must be true for trusted records |
| `key_id` | string | yes | secret version identifier, never secret material |
| `trace_id` | string | yes | bounded correlation ID |
| `processing_status` | enum | yes | defined state machine |
| `attempt` | int | yes | non-negative and bounded |
| `normalized` | object | yes | event-specific strict model |

## 5. Event-specific fields

### `push`

- ref;
- before/after SHA;
- created/deleted/forced flags;
- pusher/sender identifiers;
- bounded commit identity list or summary;
- changed paths fetched separately only when authorized and required.

### `pull_request`

- action;
- PR number;
- Draft state;
- base/head refs and SHAs;
- merged state;
- author login;
- GitHub URL.

### `issues`

- action;
- Issue number;
- state/state reason;
- bounded labels;
- assignee logins;
- GitHub URL.

### `workflow_run`

- action;
- workflow/run IDs;
- run attempt;
- event;
- status/conclusion;
- head branch/SHA;
- jobs/steps availability classification;
- GitHub URL.

A run with no created steps is represented as `CI_BLOCKED_PRE_RUN`; it is not mapped to test failure.

## 6. Persistence contract

- primary key: `(repository_id, delivery_id)`;
- exact raw payload is not stored by default;
- normalized JSON is canonicalized before storage;
- `payload_sha256` detects conflicting delivery-ID reuse;
- status transitions are append-audited or transactionally versioned;
- timestamps are timezone-aware UTC;
- errors are stored as bounded codes and masked summaries;
- external side-effect identifiers are retained for idempotency.

## 7. Privacy and retention

Prohibited durable fields:

- webhook secret or signature;
- Authorization headers;
- SMTP/Slack/MLflow credentials;
- callback URL with embedded secret;
- full raw payload unless a separately approved encrypted forensic mode exists;
- email address or personal data not required by the handler;
- Holdout or Prospective values;
- model weights, datasets, logs, or arbitrary attachments.

Retention tiers:

- trusted normalized event metadata: policy-defined operational period;
- audit/status history: longer compliance/evidence period;
- dead letters: bounded review period;
- transient request buffers: memory only;
- forensic raw payload: disabled by default, separately approved and encrypted.

## 8. Compatibility

- schema changes require version increment and migration tests;
- consumers reject unknown major versions;
- additive optional fields may use minor versions;
- semantic changes require major version;
- stored events are not silently rewritten to newer semantics;
- reprocessing creates a new processing Run ID while retaining original delivery identity.

## 9. Idempotency contract

Each handler defines an idempotency key:

- email: delivery ID + adapter + template version;
- Project sync: delivery ID + Project/node/field operation;
- workflow status: workflow run ID + attempt + handler revision;
- MLflow reference: delivery ID + MLflow run ID + tag-set hash.

A successful side effect is not repeated after restart. A partially completed side effect must be reconciled before retry.

## 10. Validation evidence

Required evidence includes signed fixtures, invalid-signature fixtures, duplicate/conflict tests, canonical payload hashes, migration tests, concurrency tests, redaction tests, retention configuration, and a manifest with tool/code/config identities.