# GitHub Platform Features Foundation v1

## Status

`FACT_CHECKED / DESIGN_ONLY / IMPLEMENTATION_PENDING`

- Repository: `arumajirou/loto_forecast_platform`
- Base branch: `main`
- Base SHA: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Design date: 2026-08-06 JST
- Scope: GitHub Pages, Dependabot, Projects, Webhooks, security scanning
- Non-scope: enabling repository settings, production deployment, secret creation, merge, auto-merge

## Purpose

This document set defines the requirements, architecture, implementation sequence, tests, migration, rollback, and operational controls required to add GitHub platform features without weakening the repository's leakage prevention, reproducibility, evidence retention, or promotion boundaries.

## Verified repository facts

1. The repository is private and its default branch is `main`.
2. `.github/workflows/ci.yml` already runs CPU PyTorch installation, Ruff format, Ruff lint, compileall, and full pytest on push and pull requests.
3. Issue #58 records a repository/account-level GitHub Actions failure that occurs before workflow step creation. New Actions-based features must not be represented as executable until this blocker is resolved.
4. The root project uses `pyproject.toml`, `uv.lock`, Python `>=3.11,<3.14`, pinned Torch/Transformers components, and optional MLflow/Ray/observability dependencies.
5. The README identifies MLflow server, Grafana, Loki, Tempo, Slack, SMTP, PostgreSQL, and Ray runtime integration as not yet formally certified.
6. No existing `.github/dependabot.yml`, Pages workflow, CodeQL workflow, or `mkdocs.yml` was found on the verified base.

## Design decisions

- GitHub Pages publishes only an explicit `docs-public/` allowlist. Internal `docs/`, runs, logs, artifacts, Holdout evidence, Prospective evidence, local paths, and security findings are excluded.
- Dependabot covers the `uv` and `github-actions` ecosystems. Automatic merge is prohibited.
- GitHub Projects is the governance source for work status, not the source of truth for model registry or promotion state.
- Webhooks use HMAC-SHA256 verification, delivery-ID deduplication, fast acknowledgement, durable processing, secret masking, and audit logging.
- Existing CI remains separate from Pages, webhook, dependency, and security workflows.
- CodeQL is gated by repository ownership and GitHub Code Security eligibility. Until that gate is satisfied, OSS scanners are used as a clearly labelled fallback.

## Document map

- [REQUIREMENTS.md](REQUIREMENTS.md)
- [FUNCTIONAL_SPECIFICATION.md](FUNCTIONAL_SPECIFICATION.md)
- [BASIC_DESIGN.md](BASIC_DESIGN.md)
- [DETAILED_DESIGN.md](DETAILED_DESIGN.md)
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- [EXECUTION_SCHEDULE.md](EXECUTION_SCHEDULE.md)
- [TEST_PLAN.md](TEST_PLAN.md)
- [MIGRATION_PLAN.md](MIGRATION_PLAN.md)
- [RISK_REGISTER.md](RISK_REGISTER.md)
- [RUNBOOK.md](RUNBOOK.md)
- [HANDOFF.md](HANDOFF.md)
- [IMPLEMENTATION_PROMPT.md](IMPLEMENTATION_PROMPT.md)
- [CHANGELOG.md](CHANGELOG.md)
- [ARTIFACT_MANIFEST.md](ARTIFACT_MANIFEST.md)

## Planned implementation PRs

1. Repository settings recovery tracked by Issue #58; no feature-code workaround.
2. Dependabot foundation.
3. GitHub Projects governance and evidence export.
4. Public documentation allowlist and Pages build/deploy.
5. GitHub webhook receiver foundation.
6. OSS security scanning fallback.
7. CodeQL enablement only after eligibility and owner approval.

Each implementation increment must be a separate Draft PR from the then-current `main`, with focused local checks first and one final repository-wide verification after implementation is complete.