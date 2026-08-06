# Implementation Plan — GitHub Platform Features Foundation v1

## 1. Delivery policy

- Every increment starts from the then-current `main`.
- Every increment is opened as a Draft PR.
- No implementation branch is stacked on this documentation branch.
- Shared workflows, root dependencies, registry state, production binding, Holdout, and Prospective scope remain unchanged unless the target PR explicitly owns them.
- Focused local checks are run during development. Full pytest and final CI are run once at the final quality gate.

## 2. Phase 0 — GitHub Actions infrastructure recovery

**Tracker:** Issue #58  
**Type:** repository/account settings, not feature-code remediation  
**Exit gate:** a GitHub-hosted job creates real steps, checkout executes, logs are accessible, and a complete result is retained.

Actions:

1. Inspect Settings → Actions → General.
2. Inspect hosted-runner policy and runner groups.
3. Inspect Actions usage, budget, billing, storage, and account restrictions.
4. Preserve UI banners and API evidence.
5. Rerun only after an external setting changes.

## 3. PR-1 — Dependabot foundation

**Branch:** `agent/github-dependabot-foundation-v1`

Scope:

- `.github/dependabot.yml`;
- dependency update policy;
- compatibility checklist/template;
- configuration syntax tests;
- no root dependency upgrade in the same PR.

Acceptance:

- GitHub accepts the configuration;
- `uv` and `github-actions` ecosystems are configured;
- no auto-merge;
- bounded PR limits and schedule;
- compatibility-sensitive dependencies documented;
- no secret or callback URL.

Rollback: revert the PR or remove `.github/dependabot.yml` in a normal follow-up PR.

## 4. PR-2 — GitHub Projects governance

**Branch:** `agent/github-projects-governance-v1`

Scope:

- Project field and view definitions;
- built-in automation configuration;
- evidence export scripts or read-only commands if needed;
- screenshots and JSON exports;
- no model-registry or promotion mutation.

Acceptance:

- Issues and PRs are automatically added;
- status taxonomy preserves blocked/failed/partial states;
- Project fields do not claim authoritative production state;
- exports contain no secret values.

Rollback: disable Project workflows and archive/delete the Project only after explicit approval; repository Issues and PRs remain intact.

## 5. PR-3 — Public docs and Pages

**Branch:** `agent/github-pages-public-docs-v1`

Entry gates:

- Issue #58 resolved;
- explicit decision that the resulting site may be public, or verified private Pages capability;
- approved public content policy.

Scope:

- `docs-public/**`;
- `mkdocs.yml` and pinned docs dependencies;
- public-document audit and manifest generator;
- PR build workflow;
- main deployment workflow;
- link and deployment smoke tests.

Acceptance:

- strict local build passes;
- prohibited-path and secret negative tests pass;
- Pages artifact contains only allowlisted files;
- source commit and SHA-256 manifest retained;
- deployed site returns expected content;
- internal docs and evidence remain inaccessible.

Rollback: disable Pages deployment workflow and repository Pages setting; retain source and build evidence.

## 6. PR-4 — Webhook receiver foundation

**Branch:** `agent/github-webhook-receiver-foundation-v1`

Scope:

- strict contracts;
- raw-body HMAC verification;
- repository/event allowlists;
- body limits and secure responses;
- delivery store and idempotency;
- transactional outbox/queue abstraction;
- JSON audit logs and Prometheus metrics;
- email adapter interface, disabled external writes by default;
- focused tests and local smoke service.

Non-scope:

- production webhook registration;
- production SMTP secret;
- Slack enablement;
- MLflow promotion writes;
- Project write permission.

Acceptance:

- valid signed fixture accepted;
- invalid signature rejected;
- duplicate handling correct;
- conflicting delivery ID detected;
- persistence failure does not acknowledge success;
- no secret appears in logs/responses;
- health and metrics endpoints work;
- tests pass without external network.

Rollback: disable the endpoint/config, remove registered webhook separately, and preserve delivery/audit records.

## 7. PR-5 — Webhook adapters and deployment

**Branch:** `agent/github-webhook-adapters-v1`

Entry gate: PR-4 merged and runtime-certified.

Scope:

- SMTP email adapter;
- workflow-status handler;
- optional Project sync;
- MLflow reference-only integration;
- deployment configuration and secret references;
- operational dashboards and alerts.

Acceptance:

- real GitHub test delivery verified;
- retries and dead-letter flow verified;
- email delivery verified without raw payload leakage;
- Issue #58 zero-step workflow state classified correctly;
- MLflow outage does not lose events or mutate promotion state.

## 8. PR-6 — OSS security scanning fallback

**Branch:** `agent/github-security-fallback-v1`

Scope:

- pinned Bandit/Semgrep/detect-secrets/pip-audit or approved equivalents;
- workflow and local runner;
- SARIF/JSON reports;
- license/provenance report;
- baseline and triage documentation;
- manifests and SHA-256.

Acceptance:

- known-positive fixtures are detected;
- baseline suppressions are justified and bounded;
- scanner failure is not reported as a clean scan;
- reports verify independently.

## 9. PR-7 — CodeQL

**Branch:** `agent/github-codeql-v1`

Entry gates:

- repository ownership/plan supports private CodeQL;
- GitHub Code Security enabled;
- owner approves costs and alert policy;
- Issue #58 resolved.

Scope:

- default setup first, or minimal advanced setup only when required;
- independent workflow;
- alert triage/runbook;
- branch-protection/check policy after evidence.

Acceptance:

- CodeQL run has real steps and accessible logs;
- Python database analysis completes;
- alerts are visible and triaged;
- no unsupported success claim.

## 10. Final integration gate

After all selected increments:

- verify repository settings and workflows;
- run focused checks and one full pytest;
- verify artifacts and SHA-256;
- scan for secrets and large files;
- update README, CHANGELOG, RUNBOOK, HANDOFF;
- retain screenshots of Pages, Project, security alerts, and webhook observability where applicable;
- do not merge or mark Ready without explicit approval.