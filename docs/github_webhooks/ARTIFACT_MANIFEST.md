# Artifact Manifest — GitHub Webhook Receiver Foundation v1

## Identity

- repository: `arumajirou/loto_forecast_platform`
- feature: `webhook-foundation`
- base: `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- branch: `agent/github-webhook-receiver-foundation-v1`
- design source: PR #139 head
  `814b59d49944b234dafc9deba1cb07b230c9a348`
- status: `PARTIALLY_VERIFIED / LOCAL_FOUNDATION_EXECUTED / PRODUCTION_DISABLED`

## Included groups

| Group | Paths | Purpose |
|---|---|---|
| strict configuration | `configs/github_webhooks/**` | allowlists, limits, retry, retention |
| receiver package | `src/loto/github_webhooks/**` | authentication, normalization, store, API |
| smoke runner | `scripts/github_webhooks/**` | deterministic signed local evidence |
| focused tests | `tests/github_webhooks/**` | security, contract, concurrency, retry |
| operations docs | `docs/github_webhooks/*.md` | requirements, design, tests, runbook, handoff |
| smoke evidence | `docs/github_webhooks/evidence/smoke/**` | synthetic PASS report and hashes |
| integrity | `docs/github_webhooks/SHA256SUMS` | exact managed-file SHA-256 |

## Explicit exclusions

- existing `src/loto/api/app.py` integration;
- public callback URL and GitHub webhook registration;
- real webhook secret, signature, token, or authorization value;
- SMTP, Slack, Project, workflow-enrichment, and MLflow adapters;
- PostgreSQL production lane;
- `.github/workflows/**`;
- root `pyproject.toml` and `uv.lock`;
- Registry, Promotion, Approval, Canary, Production, evaluation, and Prediction Lock;
- Holdout, Prospective, raw data, model artifacts, or production deployment.

## Verification states

| Check | State |
|---|---|
| repository and duplicate audit | VERIFIED |
| official GitHub protocol review | VERIFIED |
| strict policy parse | PASSED |
| Python compileall | PASSED |
| focused pytest | PASSED, 22 tests |
| signed local smoke | PASSED |
| concurrency/idempotency | PASSED |
| retry/recovery/dead letter | PASSED |
| source line length | PASSED |
| focused secret-pattern scan | PASSED |
| managed-file size scan | PASSED |
| managed SHA-256 | PASSED |
| Ruff | UNAVAILABLE |
| mypy | UNAVAILABLE |
| full repository pytest | EXECUTION_PENDING |
| GitHub Actions | BLOCKED_BY_ISSUE_58 |
| public/production receiver | NOT_EXECUTED |
| merge readiness | NOT_CLAIMED |

## Integrity procedure

`SHA256SUMS` covers every committed file in this package except itself. The list is generated from
the exact UTF-8 bytes in the local isolated implementation after final focused verification.
Verification must recompute every entry from the exact branch head.

The smoke evidence contains no secret, signature, raw request body, authorization header, or
external adapter receipt.
