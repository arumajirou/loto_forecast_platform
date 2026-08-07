# Changelog — GitHub Dependabot Foundation

## 0.1.0 — 2026-08-06

### Added

- `.github/dependabot.yml` for the `uv` and `github-actions` ecosystems.
- Explicit weekly Asia/Tokyo schedules and bounded open version-update PR counts.
- Routine minor/patch grouping with compatibility-sensitive Python exclusions.
- Repository-owned configuration policy tests.
- Requirements, operating guide, test plan, verification report, handoff and artifact manifest.

### Verification

- Exact branch contents reconstructed and checked against Git blob identities.
- PyYAML parse and policy inspection passed.
- Owned-path compileall passed.
- Focused pytest passed: 5 tests.
- Focused secret-pattern, line-length, file-size and SHA-256 checks passed.
- Ruff was unavailable in the isolated interpreter and is not reported as passed.
- Full repository pytest and GitHub runtime acceptance remain pending.

### Safety controls

- No auto-merge.
- No private registry or credential configuration.
- No dependency or `uv.lock` update.
- No change to the existing CI workflow.
- No registry, promotion, approval, canary, production, evaluation or prediction-lock mutation.
- No Holdout or Prospective publication.

### Known blockers

- Issue #58 continues to block GitHub-hosted jobs before step creation.
- Dependabot parsing and generated PR behavior cannot be verified until the configuration reaches
  the default branch.
