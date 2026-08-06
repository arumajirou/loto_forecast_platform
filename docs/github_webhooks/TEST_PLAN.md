# Test Plan — GitHub Webhook Receiver Foundation v1

## Focused commands

```bash
uv run python -m compileall -q \
  src/loto/github_webhooks \
  scripts/github_webhooks \
  tests/github_webhooks

uv run pytest -q tests/github_webhooks
```

Run Ruff and mypy when those tools are available:

```bash
uv run ruff format --check \
  src/loto/github_webhooks \
  scripts/github_webhooks \
  tests/github_webhooks

uv run ruff check \
  src/loto/github_webhooks \
  scripts/github_webhooks \
  tests/github_webhooks

uv run mypy src/loto/github_webhooks scripts/github_webhooks
```

## Unit and security cases

- valid active and previous secret signatures;
- missing, SHA-1, malformed-length, non-hex, and wrong signatures;
- invalid signature evaluated before malformed JSON;
- UTF-8 and duplicate JSON key rejection;
- exact repository ID and full-name allowlists;
- exact event/action allowlists;
- unsupported event returns an unprocessable result;
- strict policy rejects unknown configuration keys;
- body size and content-type boundaries;
- sensitive raw fields excluded from normalized persistence.

## Idempotency and concurrency cases

- new delivery produces one delivery and one outbox row;
- same delivery and same hash returns duplicate;
- same delivery and different hash returns conflict;
- eight concurrent identical requests produce one accepted record and seven duplicates;
- no duplicate handler execution record is created.

## Retry cases

- ready outbox claim increments attempt;
- transient failure schedules bounded retry;
- retry is not claimable before `available_at`;
- expired processing lease recovers to retry;
- permanent failure creates one dead letter;
- successful final handler marks the delivery processed;
- error storage accepts bounded codes only.

## HTTP and observability cases

- valid POST returns 202;
- disabled receiver returns 503;
- health reports no raw-payload persistence and no adapters;
- response excludes the internal `status_code` field;
- metrics include event/result but exclude delivery ID, sender, repository, branch, SHA, and Run ID;
- `steps=None` remains `CI_BLOCKED_PRE_RUN`.

## Smoke test

```bash
RUN_ID="webhook-smoke-$(date -u +%Y%m%dT%H%M%SZ)"

uv run python scripts/github_webhooks/smoke_receiver.py \
  --policy configs/github_webhooks/receiver_v1.yaml \
  --output "artifacts/github-webhook-smoke/${RUN_ID}"
```

Required output:

```text
SMOKE_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

The report must show first request 202, duplicate 200, one delivery, one outbox row, and false
values for raw payload, signature, and secret persistence.

## Not covered by local foundation tests

- public HTTPS and certificate verification;
- real GitHub webhook registration and delivery log;
- GitHub source IP allowlist maintenance;
- target-host secret manager;
- PostgreSQL multi-process semantics;
- real worker timeout and process termination;
- SMTP, Project, workflow-status enrichment, or MLflow adapters;
- production retention, backup, restore, alerting, or disaster recovery;
- GitHub Actions while Issue #58 remains a zero-step pre-run blocker.
