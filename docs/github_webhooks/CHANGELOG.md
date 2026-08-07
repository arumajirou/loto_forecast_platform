# Changelog — GitHub Webhook Receiver Foundation

## 0.1.0 — 2026-08-06

### Added

- strict disabled-by-default receiver policy;
- raw-body HMAC-SHA256 verification with active/previous key rotation;
- strict headers, repository, event, action, and event-model validation;
- duplicate-key-safe JSON parsing and payload SHA-256;
- SQLite delivery, outbox, status-history, and dead-letter schema;
- atomic idempotent persistence and changed-hash conflict rejection;
- bounded retry, deterministic jitter, lease recovery, and completion transitions;
- isolated FastAPI router factory and health endpoint;
- injected low-cardinality Prometheus metrics;
- signed local smoke and immutable evidence output;
- 22 focused tests and operations documentation.

### Safety

- receiver remains disabled in committed configuration;
- no public callback or GitHub webhook registration;
- no real secret, callback URL, signature, or credential;
- no adapter, SMTP, Slack, Project, MLflow, model, or production side effect;
- no dependency, lock, existing API app, or workflow change;
- no Holdout or Prospective access.

### Verification limitations

- Ruff and mypy unavailable;
- complete repository regression suite not executed;
- Issue #58 blocks actionable GitHub Actions evidence;
- production HTTPS, PostgreSQL, worker, retention, backup, and adapter evidence remain pending.
