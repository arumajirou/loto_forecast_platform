# Verification Report — GitHub Webhook Receiver Foundation v1

## Status

`PARTIALLY_VERIFIED / LOCAL_FOUNDATION_EXECUTED / FOCUSED_TESTS_PASSED /
PRODUCTION_REGISTRATION_NOT_PERFORMED`

## Verified repository facts

- repository is private and owned by personal account `arumajirou`;
- authenticated repository permission is admin;
- default branch is `main`;
- base SHA at branch creation is
  `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- PR #139 remains Open, Draft, and unmerged and was used read-only with owner authorization;
- no same-name branch or same-purpose implementation PR or Issue existed before branch creation;
- no existing `src/loto/github_webhooks` or matching receiver configuration existed on `main`;
- Issue #58 remains the repository-wide Actions pre-run blocker.

## Official protocol facts applied

- webhook authenticity is verified with a secret and `X-Hub-Signature-256`;
- the signature is HMAC-SHA256 over the payload contents;
- comparison uses a timing-safe operation;
- `X-GitHub-Delivery` is a globally unique delivery identifier;
- the receiver should return a 2xx response within 10 seconds;
- work that may exceed the request budget should be queued;
- failed deliveries are not automatically redelivered by GitHub.

## Implemented controls

- disabled-by-default strict policy;
- exact raw-byte signature verification before JSON parsing;
- active and previous key support with key-ID-only persistence;
- 2 MiB body limit and JSON content-type enforcement;
- UUID delivery ID, repository, event, and action allowlists;
- strict normalization for four event types;
- duplicate JSON key rejection;
- canonical payload SHA-256;
- atomic delivery, history, and outbox persistence;
- same-hash duplicate and changed-hash conflict handling;
- bounded retry, deterministic jitter, processing-lease recovery, and dead letter;
- isolated FastAPI router and health endpoint;
- bounded Prometheus labels;
- signed local smoke and evidence generation;
- no raw payload, signature, or secret persistence.

## Focused verification executed

Run identity: `github-webhook-foundation-isolated-20260806T0930Z`

| Check | Result |
|---|---|
| Python compileall | PASS |
| focused pytest | PASS, 22 tests |
| signed receiver smoke | PASS |
| valid first delivery | 202 |
| same-hash duplicate | 200 |
| persistent delivery count | 1 |
| persistent outbox count | 1 |
| concurrency deduplication | PASS, 1 accepted and 7 duplicates |
| retry, lease recovery, dead letter | PASS |
| FastAPI request and health contract | PASS |
| low-cardinality metrics assertions | PASS |
| source line length | PASS, no managed line above 100 |
| focused secret-pattern scan | PASS |
| managed file size scan | PASS, no file above 1 MiB |

The Python runtime emitted an unrelated `artifact_tool` spreadsheet warmup traceback on stderr.
Compileall, pytest, and smoke returned exit code 0, and the webhook package does not import that
tool.

## Unavailable or not executed

- Ruff: unavailable in the isolated interpreter;
- mypy: unavailable in the isolated interpreter;
- full repository pytest and coverage: no complete private checkout;
- repository-wide secret, dependency, and large-file scans;
- PostgreSQL implementation and tests;
- real HTTPS endpoint and target-host runtime;
- real secret-manager load and rotation;
- GitHub webhook registration, delivery log, redelivery, and URL smoke;
- email, Slack, Project, workflow enrichment, and MLflow adapters;
- production retention purge;
- backup, restore, HA, and load testing;
- successful GitHub Actions execution.

Unavailable and unexecuted checks are not represented as passed.

## Actions classification

Issue #58 remains `ACTIONS_BLOCKED_PRE_RUN`. A workflow job with absent steps and unavailable logs
is
not a webhook source or test failure. No repeated rerun is requested without an administrative
condition change.

## Authority boundary

- existing API app changed: NO
- public route registered: NO
- GitHub webhook created: NO
- real secret committed: NO
- adapter side effect executed: NO
- Registry, Promotion, Approval, Canary, or Production changed: NO
- evaluation or Prediction Lock changed: NO
- Holdout or Prospective opened or published: NO
- root dependency or `uv.lock` changed: NO
- existing workflow changed: NO

## Remaining production evidence

A future deployment must retain exact code/config/data hashes, process IDs, host/runtime identity,
TLS and callback configuration, secret key IDs, database migration evidence, signed real delivery
evidence, acknowledgement duration, persisted normalized record, outbox claim and completion,
metrics, masked logs, restart recovery, failure injection, rollback, artifact manifest, and
SHA-256 verification.
