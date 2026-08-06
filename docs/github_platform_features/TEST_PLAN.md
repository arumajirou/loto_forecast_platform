# Test Plan — GitHub Platform Features Foundation v1

## 1. Test objectives

- Verify configuration syntax and least-privilege behavior.
- Prove public documentation isolation and secret safety.
- Prove webhook authenticity, idempotency, persistence, retry, and observability.
- Distinguish execution success from configuration presence.
- Prevent GitHub governance features from mutating model registry, promotion, Holdout, Prospective, or production binding.

## 2. Test levels

| Level | Scope | Required evidence |
|---|---|---|
| Static | YAML, Python, Markdown, permissions | Ruff, mypy, parser/linter output |
| Unit | signature, schemas, filters, dedup, redaction | pytest and coverage |
| Contract | HTTP headers/body/status and event normalization | request/response fixtures |
| Integration | store/outbox, SMTP stub, MLflow stub, Project stub | isolated service logs |
| Security | replay, tampering, secret leakage, path traversal | negative-test report |
| Runtime smoke | local FastAPI and real signed fixture | PID, port, health, metrics, logs |
| GitHub acceptance | Dependabot/Pages/Actions/CodeQL | real GitHub run/settings evidence |

## 3. Dependabot tests

- YAML parse and schema review.
- `uv` ecosystem points to `/`.
- `github-actions` ecosystem points to `/`.
- schedules and open PR limits are bounded.
- no auto-merge setting or workflow is introduced.
- compatibility-sensitive dependencies are not silently grouped into unattended major updates.
- first Dependabot PR contains reviewable dependency and lock diffs.
- `uv sync --frozen` or approved equivalent succeeds on the exact PR head.
- focused runtime smoke is selected based on changed dependency ownership.

## 4. Projects tests

- all required fields exist with documented option values;
- opened Issue and PR are added automatically;
- merged PR and closed Issue transition to Done;
- blocked label maps to Blocked;
- Draft PR does not become Verified automatically;
- `FAILED` and `PARTIALLY_VERIFIED` remain representable;
- Project changes do not alter PlatformRegistry or promotion state;
- read-only export contains no token or secret;
- screenshots and JSON exports match the configured Project.

## 5. Pages tests

### Positive

- strict build succeeds from `docs-public/`;
- internal links and navigation resolve;
- generated manifest lists every deployed file with size and SHA-256;
- deployment artifact corresponds to the exact source commit;
- deployed root and selected pages return expected content.

### Negative

- symlink inside `docs-public/` is rejected;
- `../docs/` traversal is rejected;
- Linux, WSL, and Windows absolute paths are detected;
- token-like and private-key fixtures are detected;
- blocked `runs/`, `artifacts/`, logs, database, Holdout, and Prospective references fail;
- oversized or non-allowlisted file types fail;
- external embeds outside allowlist fail;
- build failure prevents deployment.

### Visibility

Before activation, verify whether the site is public or private under the actual owner and plan. A private repository alone is not accepted as proof of a private Pages site.

## 6. Webhook unit tests

- known valid HMAC fixture passes;
- wrong secret, changed body, malformed prefix, wrong hex length, missing header fail;
- comparison uses constant-time API;
- body is verified before JSON parsing;
- valid supported event normalizes correctly;
- unsupported event and action fail or are ignored by documented policy;
- unknown normalized keys fail in strict models;
- payload SHA-256 is stable;
- sensitive values are absent from normalized records and logs.

## 7. Webhook contract tests

| Case | Expected |
|---|---|
| valid new delivery | 202, persisted, queued |
| valid duplicate same hash | 200, no second handler execution |
| delivery ID reused with different hash | security rejection/conflict |
| invalid signature | 401, no persistence of trusted event |
| malformed JSON after valid signature | 400/422 |
| oversized body | 413 |
| unsupported content type | 415 |
| store unavailable | 503, no false acknowledgement |
| queue unavailable after transactional persistence | accepted only if outbox guarantees recovery |

## 8. Webhook integration tests

- SQLite local store migration and rollback;
- PostgreSQL lane when enabled;
- two concurrent identical deliveries create one processing record;
- process restart resumes queued outbox work;
- transient handler failure retries with bounded backoff;
- permanent failure enters dead letter;
- SMTP stub receives redacted normalized message;
- MLflow stub receives references only;
- Project stub updates governance fields only;
- workflow run with `steps=null` is classified `CI_BLOCKED_PRE_RUN`.

## 9. Observability tests

- required Prometheus metrics exist;
- metric labels are bounded;
- trace and delivery IDs correlate request and handler logs;
- secrets, signatures, raw authorization, SMTP credentials, and full payload do not appear;
- health distinguishes receiver, store, queue, SMTP, and MLflow states;
- shutdown drains or safely preserves queued work.

## 10. Security scanning tests

- known vulnerable test dependency is detected in an isolated fixture;
- known Bandit/Semgrep issue is detected;
- known fake secret is detected;
- allowlisted false positive requires reason and bounded scope;
- scanner crash produces `FAILED`, not a clean report;
- SARIF/JSON and manifest hashes verify;
- CodeQL test is `BLOCKED` until entitlement and Actions execution are verified.

## 11. Regression tests

- existing `ci.yml` behavior remains unchanged unless separately approved;
- existing API health, auth, metrics, model-plan, registry, sealing, and evaluation tests pass;
- no new network dependency in unit tests;
- no change to evaluation splits, protocol hash, prediction lock, or production binding;
- no root lock change in documentation-only or settings-only PRs.

## 12. Final verification commands

Implementation PRs should use `uv` and repository-owned commands. Typical final gate:

```bash
uv sync --extra dev
uv run ruff format --check src scripts tests
uv run ruff check src scripts tests
uv run mypy <owned typed paths>
uv run python -m compileall -q src scripts tests
uv run pytest -q <focused paths>
uv run pytest -q
```

Security and feature-specific commands are added by their owning PR. Commands must save stdout, stderr, exit code, environment summary, and artifact paths. GitHub CI is run once after local verification and only after Issue #58 changes materially.