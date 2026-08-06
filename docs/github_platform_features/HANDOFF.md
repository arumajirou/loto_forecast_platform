# Handoff — GitHub Platform Features Foundation v1

## Current state

`DESIGN_PACKAGE_PUSHED / DRAFT_PR_PENDING / IMPLEMENTATION_NOT_STARTED`

- Repository: `arumajirou/loto_forecast_platform`
- Base branch: `main`
- Base SHA at branch creation: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Working branch: `agent/github-platform-features-foundation-v1`
- Scope: documentation and implementation design only

## Completed

- Re-audited default branch and latest visible `main` HEAD.
- Searched same-purpose branches, PRs, and Issues; no duplicate foundation package was found.
- Confirmed existing CI and Issue #58 pre-step Actions blocker.
- Confirmed absence on the verified base of Dependabot, Pages, CodeQL, and MkDocs configuration files.
- Defined requirements, functional behavior, architecture, detailed schemas, implementation PR split, schedule, tests, migration, rollback, risks, runbook, and reusable prompt.
- Pushed all documents to an isolated remote branch.

## Not executed or not verified

- No GitHub repository/account setting was changed.
- No Project was created.
- No Pages site was enabled or deployed.
- No webhook was registered and no secret was created.
- No Dependabot or security-scanning configuration was added.
- No CodeQL entitlement was proven.
- No local Markdown lint, link check, secret scan, or full repository tests were run through this connector workflow.
- No GitHub Actions success is claimed; Issue #58 remains the controlling blocker unless later evidence supersedes it.
- No feature runtime, MLflow linkage, SMTP delivery, Project sync, or database migration was executed.

## Owner decisions required

1. Resolve Issue #58 through Actions settings, runner policy, usage/budget, billing, or account support evidence.
2. Decide whether Pages content may be public under the actual repository owner and plan.
3. Decide whether to move/use an organization and GitHub Code Security for private CodeQL.
4. Confirm Project ownership and visibility.
5. Select production webhook hosting, PostgreSQL/SQLite lane, retention, SMTP adapter, and secret store.
6. Approve the order and scope of implementation PRs.

## Recommended next action

Start with a separate Draft PR for Dependabot foundation because it has the smallest runtime surface and does not require Pages visibility or webhook hosting. GitHub Projects governance can proceed in parallel using built-in automation. Pages deployment, Actions-based security workflows, and CodeQL must wait for their gates.

## First implementation branch

```text
agent/github-dependabot-foundation-v1
```

Required owned paths:

```text
.github/dependabot.yml
docs/github_platform_features/dependabot/**
```

Do not upgrade dependencies in the same PR. Validate configuration, policy, compatibility review, and rollback only.

## Review checklist for this documentation PR

- [ ] all changed files are under `docs/github_platform_features/`;
- [ ] facts and blockers match current repository evidence;
- [ ] official references are current;
- [ ] no secret, callback URL, private hostname, local credential path, Holdout, or Prospective evidence;
- [ ] no unsupported CodeQL or private Pages claim;
- [ ] PR remains Draft;
- [ ] no merge or Ready transition;
- [ ] future implementation starts from then-current `main`, not this docs branch.

## Rollback

Before merge, close the Draft PR and delete the remote branch only after explicit approval. After merge, revert the documentation commit history through a normal PR. Never force push or rewrite `main` history.