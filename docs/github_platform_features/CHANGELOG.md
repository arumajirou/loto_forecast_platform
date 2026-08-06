# Changelog — GitHub Platform Features Foundation

All notable changes to this design package are documented here.

## 0.1.1 — 2026-08-06

### Changed

- Replaced the compact reusable prompt with an authoritative, evidence-first execution prompt for one feature increment at a time.
- Added explicit handling for an unmerged or Draft design PR: implementation must use merged `main` documentation or explicit `owner-authorized-draft` approval, and must never branch from the documentation branch.
- Added feature-specific entry gates for Dependabot, Projects, Pages, webhook foundation, webhook adapters, OSS security fallback, and CodeQL.
- Added a precise GitHub Actions classification for verified execution, pre-run blocking, actionable failure, and unknown evidence.
- Added owned-path allowlisting, duplicate detection, current-main re-audit, status taxonomy, stop conditions, rollback requirements, pre-push audit, Draft PR body requirements, and a fixed final-report schema.
- Added explicit owner-action handling when GitHub Projects, Pages, plan, billing, GitHub Code Security, or other settings cannot be changed or proven through the available connector/API.
- Preserved all authority boundaries around registry, promotion, approval, production binding, evaluation, prediction locks, Holdout, Prospective, secrets, and callback URLs.

### Verification status

- Remote file update: `EXECUTED`.
- Semantic alignment with the existing requirements, implementation plan, execution schedule, and test plan: `PARTIALLY_VERIFIED`.
- Local Markdown lint, link check, secret scan, portable export, and SHA-256 package: `EXECUTION_PENDING`.
- Feature implementation and runtime verification: `NOT_IN_SCOPE`.

## 0.1.0 — 2026-08-06

### Added

- Repository fact-check report for GitHub Pages, Dependabot, Projects, Webhooks, security scanning, and CodeQL eligibility.
- Requirements and acceptance criteria with explicit evidence statuses and scope boundaries.
- Functional specification covering event contracts, status transitions, Pages allowlists, Dependabot policy, Project governance, MLflow linkage, and security fallback.
- Basic and detailed architecture designs.
- Staged implementation plan using independent Draft PRs from current `main`.
- Dependency-driven execution schedule and stop conditions.
- Focused, integration, security, and final quality test plan.
- Additive migration and rollback plan.
- Risk register including Issue #58, Pages visibility, dependency compatibility, webhook authenticity/replay, and CodeQL eligibility.
- Cross-platform operational runbook.
- Reusable implementation prompt.
- Handoff and artifact manifest framework.

### Verified facts retained

- Base branch `main`.
- Base SHA `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0` at design branch creation.
- Existing CI performs CPU Torch installation, Ruff, compileall, and full pytest.
- Issue #58 remains the canonical GitHub Actions pre-step infrastructure blocker at the time of design.
- No existing Dependabot, Pages, CodeQL, or MkDocs configuration was found on the verified base.

### Not changed

- No feature implementation.
- No repository/account setting.
- No GitHub secret, variable, environment, Project, webhook registration, Pages activation, CodeQL activation, or branch protection.
- No root dependency or lock file.
- No model, evaluation, registry, promotion, prediction lock, Holdout, Prospective, or production binding.

### Known blockers

- GitHub Actions execution must be recovered and verified through Issue #58.
- Pages visibility requires owner/plan verification and explicit approval.
- Private CodeQL availability requires repository ownership/plan/GitHub Code Security verification.
