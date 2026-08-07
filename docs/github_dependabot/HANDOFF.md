# Handoff — GitHub Dependabot Foundation v1

## Current state

- Configuration and repository-owned policy test are committed on
  `agent/github-dependabot-foundation-v1`.
- The branch was created directly from
  `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`.
- No dependency, lock, source runtime or existing CI workflow change is included.
- Runtime acceptance remains pending because Dependabot reads the configuration from the default
  branch and Issue #58 blocks actionable GitHub-hosted CI evidence.

## Reviewer focus

1. confirm `uv` and `github-actions` are the only intended ecosystems;
2. confirm schedule and open-PR limits are appropriately bounded;
3. review the compatibility-sensitive exclusion list;
4. verify no custom labels are required before activation;
5. confirm auto-merge remains disabled;
6. inspect the test for false-positive or false-negative policy assumptions;
7. confirm authority boundaries and rollback steps.

## Required local verification

```bash
uv run ruff format --check tests/github_platform/test_dependabot_config.py
uv run ruff check tests/github_platform/test_dependabot_config.py
uv run python -m compileall -q tests/github_platform
uv run pytest -q tests/github_platform/test_dependabot_config.py
```

After these pass, run the full repository suite once. Do not repeatedly trigger GitHub CI while
Issue #58 still produces zero-step jobs.

## Post-merge verification

1. inspect Dependabot status and job logs for both ecosystems;
2. retain successful parse evidence;
3. inspect the first generated PR for each ecosystem;
4. verify default labels, grouping and PR limits;
5. run frozen-lock and focused compatibility checks on generated PR heads;
6. update `VERIFICATION_REPORT.md` in a follow-up PR with exact evidence.

## Owner actions

- Resolve Issue #58 through repository/account Actions permissions, budget/billing, runner policy
  or GitHub Support as applicable.
- Optionally create a `compatibility-review` repository label. Do not add it to Dependabot config
  until the label exists and a separate reviewed change is approved.

## Next safe increment

After this PR is reviewed and the default-branch behavior is verified, proceed to the separately
planned GitHub Projects governance increment. Do not combine that work into this branch.
