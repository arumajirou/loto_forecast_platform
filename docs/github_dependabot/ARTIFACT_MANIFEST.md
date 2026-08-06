# Artifact Manifest — GitHub Dependabot Foundation v1

## Identity

- Repository: `arumajirou/loto_forecast_platform`
- Base: `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Branch: `agent/github-dependabot-foundation-v1`
- Design source: PR #139 head `814b59d49944b234dafc9deba1cb07b230c9a348`
- Feature: `dependabot`
- Status: `EXECUTED / PARTIALLY_VERIFIED / GITHUB_ACCEPTANCE_PENDING`

## Included files

| Path | Purpose |
|---|---|
| `.github/dependabot.yml` | bounded version-update configuration |
| `tests/github_platform/test_dependabot_config.py` | repository-owned policy checks |
| `docs/github_dependabot/README.md` | configuration and review guide |
| `docs/github_dependabot/REQUIREMENTS.md` | functional and non-functional requirements |
| `docs/github_dependabot/TEST_PLAN.md` | focused, negative and acceptance tests |
| `docs/github_dependabot/RUNBOOK.md` | operations, incidents and rollback |
| `docs/github_dependabot/VERIFICATION_REPORT.md` | verified facts and non-claims |
| `docs/github_dependabot/CHANGELOG.md` | implementation history |
| `docs/github_dependabot/HANDOFF.md` | reviewer and post-merge handoff |
| `docs/github_dependabot/ARTIFACT_MANIFEST.md` | this package inventory |
| `docs/github_dependabot/SHA256SUMS` | independently reproducible file hashes |

## Explicit exclusions

- `pyproject.toml` and `uv.lock` changes;
- dependency upgrades;
- changes to `.github/workflows/ci.yml`;
- auto-merge or branch-protection changes;
- private registry definitions or credentials;
- GitHub account/repository settings mutations;
- model, registry, promotion, approval, canary or production changes;
- evaluation, prediction-lock, Holdout, Prospective or raw-data changes;
- transient logs, secrets, callback URLs and local credential paths.

## Verification states

| Check | State |
|---|---|
| repository and permission audit | VERIFIED |
| duplicate branch/PR/Issue/file audit | VERIFIED for selected feature |
| official syntax and ecosystem review | VERIFIED |
| files written to feature branch | EXECUTED |
| static semantic review | PARTIALLY_VERIFIED |
| local YAML parse/Ruff/compileall/pytest | EXECUTION_PENDING |
| GitHub Dependabot parse/job | EXECUTION_PENDING until default branch |
| generated update PR behavior | EXECUTION_PENDING |
| GitHub Actions | BLOCKED_BY_ISSUE_58 |
| merge readiness | NOT_CLAIMED |

## Integrity procedure

`SHA256SUMS` is generated from the exact UTF-8 contents fetched back from the implementation branch.
It covers all included files except `SHA256SUMS` itself. Verification must recompute hashes from the
same branch/ref and compare every entry. Git blob identities remain available independently through
GitHub.
