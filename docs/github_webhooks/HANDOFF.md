# Handoff — GitHub Webhook Receiver Foundation v1

## Current state

- branch: `agent/github-webhook-receiver-foundation-v1`
- committed policy: disabled
- local persistence: SQLite
- dispatch target: durable `dispatch-v1` outbox only
- public callback: not registered
- real secret: not created or stored
- adapters: disabled and not implemented in this increment
- GitHub Actions: blocked before step creation by Issue #58

## Reviewer focus

1. raw-body verification ordering and constant-time comparison;
2. active/previous secret rotation boundary;
3. repository, event, and action allowlists;
4. event-specific normalized field minimization;
5. SQLite transaction, uniqueness, retry, and lease behavior;
6. response codes for accepted, duplicate, conflict, invalid, and unavailable cases;
7. absence of raw payload, signature, secret, and unneeded personal data;
8. bounded metric labels and safe log metadata;
9. disabled default and lack of existing-app integration;
10. production deployment and adapter work remaining separate.

## Required repository-native verification

```bash
uv sync --extra dev --extra api
uv run ruff format --check \
  src/loto/github_webhooks \
  scripts/github_webhooks \
  tests/github_webhooks
uv run ruff check \
  src/loto/github_webhooks \
  scripts/github_webhooks \
  tests/github_webhooks
uv run mypy src/loto/github_webhooks scripts/github_webhooks
uv run python -m compileall -q src/loto/github_webhooks scripts/github_webhooks
uv run pytest -q tests/github_webhooks
uv run pytest -q
```

Run GitHub Actions once only after Issue #58 materially changes.

## Next separate increment

`webhook-adapters` must not start until this foundation is merged and target-host runtime
certification proves signed ingestion, durable persistence, restart recovery, and bounded worker
execution. The next branch must start from the then-current `main`, not this branch.

Email remains the default notification adapter. Slack remains optional and disabled. Project writes
must be governance-only. MLflow writes must be reference-only and cannot mutate Registry, Promotion,
Approval, Canary, or Production state.
