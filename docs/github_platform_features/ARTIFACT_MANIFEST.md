# Artifact Manifest — GitHub Platform Features Foundation v1

## Package identity

- Repository: `arumajirou/loto_forecast_platform`
- Branch: `agent/github-platform-features-foundation-v1`
- Base: `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Package type: design documentation only
- Status: `EXECUTED_GITHUB_WRITE / CONTENT_REVIEW_PENDING / IMPLEMENTATION_PENDING`

## Included artifacts

| Path | Purpose | Status |
|---|---|---|
| `README.md` | package index and decisions | CREATED |
| `FACT_CHECK_REPORT.md` | repository and official-capability verification | CREATED |
| `REQUIREMENTS.md` | functional/non-functional requirements | CREATED |
| `FUNCTIONAL_SPECIFICATION.md` | feature behavior and contracts | CREATED |
| `BASIC_DESIGN.md` | logical architecture and boundaries | CREATED |
| `DETAILED_DESIGN.md` | schemas, workflows, permissions, retries, metrics | CREATED |
| `IMPLEMENTATION_PLAN.md` | independent implementation PR plan | CREATED |
| `EXECUTION_SCHEDULE.md` | dependency-driven engineering schedule | CREATED |
| `TEST_PLAN.md` | static/unit/contract/integration/security/acceptance tests | CREATED |
| `MIGRATION_PLAN.md` | additive migration and rollback | CREATED |
| `RISK_REGISTER.md` | identified risks and mitigations | CREATED |
| `RUNBOOK.md` | cross-platform operations and incident procedures | CREATED |
| `IMPLEMENTATION_PROMPT.md` | reusable implementation instruction | CREATED |
| `CHANGELOG.md` | package change history | CREATED |
| `HANDOFF.md` | implementation handoff and remaining gates | CREATED after this manifest |

## Excluded artifacts

- implementation source code;
- GitHub repository/account setting exports;
- Project screenshots or JSON exports;
- Pages build output;
- workflow run logs;
- webhook runtime evidence;
- security scan reports;
- MLflow/PostgreSQL evidence;
- secrets, variables, callback URLs, or credentials;
- Holdout or Prospective data/evidence.

## Integrity model

GitHub commit and blob identities are retained by the repository and the Draft PR diff. A portable `SHA256SUMS` file is not claimed for this documentation-only connector write because no local immutable export package was generated in this execution. Future implementation PRs must generate and independently verify `ARTIFACT_MANIFEST.json` and `SHA256SUMS` for code, logs, reports, screenshots, database migrations, and deployment evidence.

## Validation status

- Repository/branch creation: `EXECUTED`
- Files pushed to remote branch: `EXECUTED`
- Markdown semantic review: `PARTIALLY_VERIFIED`
- Local Markdown lint/link check: `EXECUTION_PENDING`
- Secret scan: `EXECUTION_PENDING`
- GitHub Actions: `BLOCKED_BY_ISSUE_58`
- Feature runtime: `NOT_IN_SCOPE`
- Merge readiness: `NOT_CLAIMED`

## Verification instructions

1. Review the Draft PR changed-file list.
2. Confirm all paths remain under `docs/github_platform_features/`.
3. Run Markdown lint, link check, secret scan, and repository diff review locally.
4. Generate a portable export and SHA-256 manifest only if a downloadable handoff package is required.
5. Keep the PR Draft until review and actionable CI evidence are available.