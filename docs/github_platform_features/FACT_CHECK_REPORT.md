# Fact-Check Report — GitHub Platform Features Foundation v1

## 1. Verification timestamp and scope

- Verified: 2026-08-06 JST
- Repository: `arumajirou/loto_forecast_platform`
- Verified base: `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Sources: repository metadata and files through the connected GitHub application; official GitHub documentation URLs listed below.
- This report distinguishes repository evidence, official capability constraints, design inference, and unverified settings.

## 2. Repository-derived facts

### VERIFIED

- Repository visibility is private.
- Default branch is `main`.
- The verified base has an existing `.github/workflows/ci.yml`.
- Existing CI installs matching CPU-only Torch, installs project/test dependencies, runs Ruff format, Ruff lint, compileall, and full pytest.
- Root `pyproject.toml` uses Python `>=3.11,<3.14`, `uv`/lock-oriented project structure, pinned Torch/Transformers-related components, and optional MLflow/Ray/observability dependencies.
- README references substantial Markdown specifications, plans, research logs, model inventory, and implementation status.
- README states PostgreSQL, MLflow server, Ray, Grafana, Loki, Tempo, Slack, and SMTP are not formally certified in the described environment.
- Issue #58 is open and classifies multiple Actions jobs as failing before configured steps execute.
- No file was found at the verified base for `.github/dependabot.yml`, `.github/workflows/codeql.yml`, `.github/workflows/pages.yml`, or `mkdocs.yml`.

### PARTIALLY_VERIFIED

- Existing API includes authentication, health, Prometheus metrics, model/run endpoints, and approval-related contracts. No GitHub webhook endpoint was found in the inspected API file, but a full repository symbol audit must be repeated immediately before implementation.

### UNVERIFIED SETTINGS

The connected repository/file APIs do not prove the current UI configuration or billing state for:

- Actions general policy and hosted-runner allowance;
- remaining private-repository Actions minutes, budgets, billing restrictions;
- Pages enabled state, source, custom domain, and visibility;
- Dependabot security updates UI setting;
- dependency graph availability;
- secret scanning/GitHub Secret Protection;
- GitHub Code Security entitlement;
- existing user- or organization-level Projects not linked in repository files;
- existing repository webhook registrations and secret values;
- environment protection rules and branch protection rules.

These must be checked by the repository owner and exported as evidence. Secret values must never be exported.

## 3. Capability conclusions

### GitHub Pages

**Conclusion:** suitable for an allowlisted static documentation site, not for FastAPI, MLflow, Grafana, or other dynamic services.

**Condition:** site visibility must be explicitly verified. A private repository must not be assumed to imply a private Pages site.

Official references:

- https://docs.github.com/en/pages
- https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site
- https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages

### Dependabot

**Conclusion:** strongly applicable to `uv` and GitHub Actions dependencies, with explicit compatibility review and no auto-merge.

Official references:

- https://docs.github.com/en/code-security/dependabot
- https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file
- https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories

### GitHub Projects

**Conclusion:** applicable for Issue/PR governance and evidence workflow. It must not replace PlatformRegistry, promotion, or production binding.

Official references:

- https://docs.github.com/en/issues/planning-and-tracking-with-projects
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project

### Webhooks

**Conclusion:** applicable only with a secure receiver. GitHub does not provide the project-specific signature verification, durable queue, idempotent handlers, email/MLflow semantics, or audit database.

Official references:

- https://docs.github.com/en/webhooks
- https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks
- https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/redelivering-webhooks

### Code scanning / CodeQL

**Conclusion:** eligibility is not established for the current private personal-account repository. Do not add a workflow and claim support until owner/organization/plan and GitHub Code Security availability are verified.

Official references:

- https://docs.github.com/en/code-security/code-scanning
- https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning
- https://docs.github.com/en/get-started/learning-about-github/githubs-plans

## 4. Corrections to the initial proposal

1. Markdown files do not automatically become a well-structured site; a static-site build and content policy are required.
2. A visible Security tab is not evidence that CodeQL, secret scanning, or GitHub Code Security is enabled.
3. Webhooks do not directly and safely transfer commits to Slack or MLflow without a receiver and explicit adapters.
4. Issue counts are time-sensitive and should not be hard-coded as the reason to use Projects.
5. Actions-based features cannot be considered runnable while Issue #58 remains a pre-step infrastructure blocker.
6. MLflow, Grafana, Slack, and SMTP integration is not currently certified merely because dependencies, docs, or API placeholders exist.

## 5. Required re-verification before implementation

Immediately before each feature branch:

- refresh latest `main` SHA;
- search same-purpose branches, PRs, Issues, files, and settings evidence;
- re-read current official GitHub documentation for configuration syntax and eligibility;
- confirm repository visibility/ownership/plan;
- confirm Issue #58 status;
- record exact scope, owned files, permissions, secrets boundary, tests, and rollback.

No previous observation may be promoted to a current fact without this re-verification.