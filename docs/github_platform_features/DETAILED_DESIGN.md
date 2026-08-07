# Detailed Design — GitHub Platform Features Foundation v1

## 1. Dependabot configuration

Proposed file: `.github/dependabot.yml`

```yaml
version: 2
updates:
  - package-ecosystem: uv
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "03:00"
      timezone: Asia/Tokyo
    open-pull-requests-limit: 3
    labels: [dependencies, compatibility-review]
    groups:
      routine-python:
        update-types: [minor, patch]
    ignore:
      - dependency-name: torch
        update-types: [version-update:semver-major]
      - dependency-name: transformers
        update-types: [version-update:semver-major]

  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "03:30"
      timezone: Asia/Tokyo
    open-pull-requests-limit: 2
    labels: [dependencies, github-actions]
```

Exact grouping and ignore syntax must be validated against current GitHub documentation during the implementation PR. Compatibility-sensitive dependencies are not permanently frozen by this example; they are routed to explicit review.

## 2. Pages detailed design

### 2.1 Build tooling

Preferred static site generator: MkDocs with a minimal reviewed plugin set. Theme and plugin versions are pinned through `uv.lock` or a dedicated docs lock lane.

### 2.2 Public-document audit

`audit_public_docs.py` performs:

- root containment and symlink rejection;
- extension allowlist;
- file-size limits;
- secret-pattern and high-entropy scanning;
- local absolute-path detection for Linux, WSL, and Windows;
- blocked-term and blocked-path checks;
- Markdown link target validation;
- external image/embed allowlist;
- generated manifest containing path, size, SHA-256, and source commit.

The audit uses explicit findings with severity and does not silently redact committed files. A prohibited finding blocks deployment.

### 2.3 Workflow permissions

`docs-build.yml`:

```yaml
permissions:
  contents: read
```

`pages-deploy.yml`:

```yaml
permissions:
  contents: read
  pages: write
  id-token: write
```

The deploy job uses environment `github-pages`, a concurrency group, a strict build artifact, and an approval gate where repository settings permit it.

## 3. Project configuration design

Project configuration is exported after manual creation to:

```text
docs/github_platform_features/evidence/project/
  PROJECT_FIELDS.json
  PROJECT_VIEWS.json
  PROJECT_WORKFLOWS.json
  SCREENSHOTS/
  ARTIFACT_MANIFEST.json
  SHA256SUMS
```

Exported evidence must mask private node IDs where unnecessary and must not contain tokens. Built-in automation is preferred over custom Actions until a specific gap is demonstrated.

## 4. Webhook domain model

### 4.1 Pydantic contracts

```python
class GitHubWebhookHeaders(BaseModel):
    event: str
    delivery_id: UUID
    signature_256: str
    hook_id: int | None = None

class GitHubWebhookEnvelope(BaseModel):
    delivery_id: UUID
    event_type: Literal["push", "pull_request", "issues", "workflow_run"]
    action: str | None
    repository_id: int
    repository_full_name: str
    sender_login: str | None
    ref: str | None
    head_sha: str | None
    payload_sha256: str
    received_at: AwareDatetime
    trace_id: str
```

All models use `extra="forbid"` at the normalized boundary. Raw GitHub payloads may contain additional keys and are parsed by event-specific extractors rather than directly persisted.

### 4.2 Signature verification

```text
expected = "sha256=" + HMAC_SHA256(secret, raw_body).hexdigest()
verified = hmac.compare_digest(expected, received_signature)
```

Requirements:

- verify raw bytes before JSON parsing;
- reject empty secret at startup;
- never log signature or secret;
- support active and previous secret during a bounded rotation window;
- record only `signature_verified=true/false` and rotation key identifier, not key material.

### 4.3 Request limits

- configurable maximum body size, initial recommendation 2 MiB;
- content type must be JSON;
- request timeout below upstream timeout;
- no external network call before event persistence;
- handler execution outside request path.

### 4.4 Deduplication

Unique key:

```text
(repository_id, delivery_id)
```

Additional integrity check:

```text
payload_sha256
```

A duplicate with the same hash returns `200 duplicate`. Reuse of a delivery ID with a different hash is a security event and returns a rejection/conflict response.

### 4.5 Store schema

```sql
CREATE TABLE github_webhook_deliveries (
  repository_id BIGINT NOT NULL,
  delivery_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  action TEXT,
  payload_sha256 TEXT NOT NULL,
  received_at TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error_code TEXT,
  trace_id TEXT NOT NULL,
  normalized_json TEXT NOT NULL,
  PRIMARY KEY (repository_id, delivery_id)
);
```

SQLite may be used for local development. PostgreSQL is preferred for multi-process production deployment. Schema migrations must be versioned and reversible.

### 4.6 Retry policy

- maximum attempts: configurable, initial recommendation 5;
- exponential backoff with jitter;
- per-handler timeout;
- retry only classified transient failures;
- permanent validation/auth failures are not retried;
- final state `DEAD_LETTER` retains masked error code and references.

## 5. Handler design

### Email handler

Input: normalized event. Output: notification record. SMTP credentials are loaded from secret storage. Body excludes raw payload and attachment bytes.

### Project-sync handler

Updates only governance fields. Missing Project permissions produce `PARTIALLY_VERIFIED`; no issue or registry state is overwritten.

### Workflow-status handler

Captures run ID, attempt, conclusion, job/step availability, and URLs. A failure with no steps is classified `CI_BLOCKED_PRE_RUN`, consistent with Issue #58, rather than a code-test failure.

### MLflow-reference handler

Writes tags/metadata to an explicitly selected integration run. It cannot call platform promotion or approval APIs.

## 6. Metrics

Recommended Prometheus metrics:

```text
github_webhook_requests_total{event,result}
github_webhook_signature_failures_total
github_webhook_duplicates_total{result}
github_webhook_ack_seconds
github_webhook_handler_seconds{handler,result}
github_webhook_queue_depth
github_webhook_dead_letters_total{handler}
github_notification_total{adapter,result}
github_pages_build_total{result}
github_security_scan_total{tool,result}
```

Repository name, sender login, branch name, delivery ID, commit SHA, and Run ID must not be unbounded metric labels. They belong in logs/traces.

## 7. Logging and tracing

Every event log includes timestamp UTC, level, component, event type, delivery ID, trace ID, repository ID, status transition, attempt, duration, and masked error code. Secret values, raw authorization headers, SMTP credentials, and full payloads are prohibited.

OpenTelemetry spans cover request verification, persistence, queue wait, handler execution, notification, and MLflow linkage.

## 8. Security workflow design

The fallback workflow emits machine-readable reports and a manifest. Tool versions and rule revisions are pinned. A later CodeQL workflow is separate and is not enabled until eligibility is verified. Security findings require triage status, owner, justification, and closure evidence.

## 9. Configuration

Configuration is Pydantic-validated and loaded from environment variables or approved config files. Required settings include enabled flag, repository allowlist, webhook secret reference, body limit, store URL, retry limits, adapter enablement, SMTP reference, MLflow URI, and timeout values. Unknown configuration keys fail closed in strict mode.