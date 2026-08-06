# Changelog — GitHub Platform Features Foundation

All notable changes to this design package are documented here.

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