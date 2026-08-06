# Implementation Prompt — GitHub Platform Features

Use this prompt for one implementation increment at a time. Replace only the variables and selected feature scope.

```text
@GitHub

Repository:
https://github.com/arumajirou/loto_forecast_platform

You are the lead engineer responsible for GitHub platform integration, security, reproducibility, and operational evidence.

TARGET_FEATURE=<dependabot|projects|pages|webhook-foundation|webhook-adapters|security-fallback|codeql>
TARGET_PR=<descriptive PR name>
BRANCH=agent/<unique-feature-branch>
PR_MODE=Draft

Authoritative design documents:

- docs/github_platform_features/README.md
- docs/github_platform_features/FACT_CHECK_REPORT.md
- docs/github_platform_features/REQUIREMENTS.md
- docs/github_platform_features/FUNCTIONAL_SPECIFICATION.md
- docs/github_platform_features/BASIC_DESIGN.md
- docs/github_platform_features/DETAILED_DESIGN.md
- docs/github_platform_features/IMPLEMENTATION_PLAN.md
- docs/github_platform_features/EXECUTION_SCHEDULE.md
- docs/github_platform_features/TEST_PLAN.md
- docs/github_platform_features/MIGRATION_PLAN.md
- docs/github_platform_features/RISK_REGISTER.md
- docs/github_platform_features/RUNBOOK.md

## 0. Start-of-work re-audit

Before changing anything, retrieve and report:

1. repository visibility, owner, permissions, and default branch;
2. latest `main` HEAD SHA immediately before branch creation;
3. same-name and same-purpose branches, open/closed PRs, Issues, and files;
4. current `.github/**`, root `pyproject.toml`, root `uv.lock`, API integration paths, security and observability paths relevant to TARGET_FEATURE;
5. Issue #58 status and latest actionable workflow evidence;
6. current official GitHub documentation for TARGET_FEATURE, including eligibility and configuration syntax;
7. settings or plan facts that cannot be proven through repository APIs, clearly marked `OWNER_UI_VERIFICATION_REQUIRED`.

If duplicate implementation exists, stop and report it. Do not create another branch.

## 1. Git safety

- Create the branch from the then-current `main` only.
- No direct write to `main`.
- No force push, rebase, reset, history rewrite, branch deletion, merge, auto-merge, or Ready transition.
- Keep the PR Draft.
- Do not modify unrelated worktrees or branches.
- Record base SHA, head SHA, merge-base, ahead/behind, changed paths, and final diff.

## 2. Scope rules

Implement only TARGET_FEATURE and its focused tests/docs.

Do not modify:

- model registry or production binding;
- promotion/approval semantics;
- evaluation protocol, Holdout, or Prospective data;
- prediction-lock evidence;
- unrelated providers/models;
- root dependencies or root `uv.lock` unless TARGET_FEATURE proves the change is necessary and the design explicitly authorizes it;
- existing `.github/workflows/ci.yml` unless the target scope explicitly owns a minimal reviewed change.

Issue #58 is a repository/account infrastructure blocker. Do not change feature code to work around a zero-step Actions failure without a concrete workflow error.

## 3. Required engineering controls

- strict Pydantic contracts with `extra="forbid"` for owned normalized inputs;
- typed public APIs and docstrings;
- least-privilege workflow permissions;
- timeout, bounded retry, idempotency, secret masking, audit logs, metrics, and rollback where applicable;
- atomic file writes and versioned database migrations where applicable;
- no raw webhook payload, signature, token, callback URL, SMTP credential, Holdout, or Prospective evidence in logs or artifacts;
- explicit statuses: PROPOSED, EXECUTION_PENDING, EXECUTED, VERIFIED, PARTIALLY_VERIFIED, BLOCKED, FAILED;
- no silent fallback from CodeQL, GPU, MLflow, notification, or Project integration states.

## 4. Feature-specific gates

### dependabot

Implement `uv` and `github-actions` ecosystems, bounded weekly updates, compatibility review, and no auto-merge. Do not upgrade dependencies in the same foundation PR.

### projects

Use Projects for Issue/PR governance only. Export fields/views/workflows and screenshots. Do not mutate model registry or promotion.

### pages

Require an explicit visibility decision. Build only `docs-public/`. Add symlink/path/secret/Holdout/Prospective checks, strict build, manifest, and separated build/deploy workflows.

### webhook-foundation

Implement raw-body HMAC-SHA256 verification, repository/event allowlists, body limits, delivery-ID deduplication, payload SHA-256, persistence/outbox, secure responses, logs, metrics, and offline tests. Keep external adapters disabled.

### webhook-adapters

Require certified foundation. Add email default, optional disabled Slack, workflow status, Project governance sync, and MLflow reference-only linkage. No promotion writes.

### security-fallback

Pin and run approved OSS dependency/SAST/secret scanners. A scanner crash is FAILED, not clean. Retain machine-readable reports and hashes.

### codeql

Do not implement until private-repository entitlement, organization/plan, GitHub Code Security, and Issue #58 recovery are verified. Start with default setup unless advanced setup is demonstrably required.

## 5. Testing policy

During development, run only focused fast checks after each change:

- Ruff on changed paths;
- mypy on owned typed paths;
- focused pytest;
- compileall;
- feature smoke and negative/security tests.

After implementation and local review are complete, run once:

- full pytest;
- coverage for owned code;
- dependency/secret/large-file scans;
- artifact manifest and SHA-256 verification;
- final GitHub Actions run only after Issue #58 has materially changed/resolved.

Do not repeatedly trigger heavy CI during iterative development.

## 6. Required deliverables

Update or create, as applicable:

- README
- REQUIREMENTS
- FUNCTIONAL_SPECIFICATION
- BASIC_DESIGN
- DETAILED_DESIGN
- TEST_PLAN
- MIGRATION_PLAN
- RISK_REGISTER
- VERIFICATION_REPORT
- CHANGELOG
- HANDOFF
- RUNBOOK
- ARTIFACT_MANIFEST
- SHA256SUMS
- logs, metrics, traces, screenshots, and database migration evidence

## 7. PR publication

Before push:

- review git status, branch, remote, and diff;
- scan for secrets and large files;
- stage only owned paths;
- commit intentionally;
- push branch;
- open a Draft PR with scope, verified facts, tests, evidence, blockers, non-claims, rollback, base/head SHAs, and Issue #58 relationship.

Do not merge or mark Ready.

## 8. Final response

Report:

- status classification;
- branch, base SHA, head SHA, PR URL;
- changed files;
- local checks actually executed and exact results;
- GitHub Actions result or BLOCKED state;
- artifacts and SHA-256 verification;
- owner settings still requiring UI verification;
- remaining risks and next approved step.
```

## Recommended use order

1. `dependabot`
2. `projects`
3. `pages` after visibility and Actions gates
4. `webhook-foundation`
5. `webhook-adapters`
6. `security-fallback`
7. `codeql` after eligibility gate