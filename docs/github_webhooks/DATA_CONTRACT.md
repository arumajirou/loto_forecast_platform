# Data Contract — GitHub Webhook Receiver Foundation v1

## Header contract

| Header | Required | Rule |
|---|---:|---|
| `Content-Type` | yes | `application/json`, optional charset |
| `X-GitHub-Event` | yes | one supported event |
| `X-GitHub-Delivery` | yes | UUID-compatible |
| `X-Hub-Signature-256` | yes | `sha256=` plus 64 hexadecimal characters |
| `X-GitHub-Hook-ID` | no | positive integer metadata |
| `User-Agent` | no | bounded, not trusted identity |

The legacy SHA-1 signature header is not accepted.

## Normalized envelope

Schema version is `1.0.0`. Durable trusted fields are:

```text
delivery_id
event_type
action
repository_id
repository_full_name
sender_login
ref
head_sha
payload_sha256
received_at
signature_verified=true
key_id
trace_id
processing_status=QUEUED
attempt=0
normalized
```

The normalized object is created from an event-specific strict Pydantic model. Extra fields from the
raw GitHub payload are ignored by the extractor and are not copied to persistence.

## Event-specific normalized fields

### push

```text
ref
before_sha
after_sha
created
deleted
forced
sender_login
```

### pull_request

```text
action
number
draft
merged
base_ref
base_sha
head_ref
head_sha
author_login
html_url
```

### issues

```text
action
number
state
state_reason
labels
assignees
author_login
html_url
```

Issue title, body, comments, email addresses, and arbitrary user objects are excluded.

### workflow_run

```text
action
workflow_id
run_id
run_attempt
trigger_event
status
conclusion
head_branch
head_sha
execution_classification
html_url
```

`steps=None` or an empty step set with unavailable logs is classified
`CI_BLOCKED_PRE_RUN`, not a code-test failure.

## SQLite tables

```text
github_webhook_schema
github_webhook_deliveries
github_webhook_outbox
github_webhook_status_history
github_webhook_dead_letters
```

Primary delivery identity is `(repository_id, delivery_id)`. Outbox identity additionally includes
the handler name.

## Prohibited durable data

- webhook secret and signature;
- authorization or cookie headers;
- callback URLs containing credentials;
- complete raw payload;
- SMTP, Slack, Project, MLflow, or database credentials;
- unneeded email or personal data;
- model weights, dataset rows, logs, or attachments;
- Holdout or Prospective actual values;
- prediction or promotion authority.

## Retention policy

The committed configuration declares:

- trusted delivery metadata: 30 days;
- status history: 180 days;
- dead letters: 30 days.

This PR records the policy but does not run an automatic purge job. A future operations increment
must implement and verify deletion order, legal hold behavior, backup interaction, and audit
evidence before enabling automated retention.

## Compatibility

Stored schema version 1 is created idempotently. Unknown normalized major versions must be rejected
by future consumers. Existing stored deliveries are never silently rewritten to newer semantics.
Reprocessing uses the same delivery identity and a separately tracked processing attempt.
