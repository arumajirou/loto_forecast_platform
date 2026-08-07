# Source Registry

Checked on 2026-08-06. Official GitHub documentation is the primary source for GitHub behavior.

| Claim | Official source |
|---|---|
| Manual dispatch requires the workflow on the default branch; input limit | https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow |
| Self-hosted runner ephemeral recommendation and outbound HTTPS 443 | https://docs.github.com/en/actions/reference/runners/self-hosted-runners |
| GitHub App installation tokens expire after one hour | https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app |
| Checks write operations and rich checks | https://docs.github.com/en/rest/checks/runs and https://docs.github.com/en/rest/guides/using-the-rest-api-to-interact-with-checks |
| Projects fields, views and automation; up to 50 fields | https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects |
| Issue Forms syntax and public-preview status | https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms |
| Ruleset controls and expected GitHub App for checks | https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets |
| Actions artifact/log retention for private repositories | https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository |
| Environment required reviewers and plan/visibility limits | https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments |

## Repository sources

- `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- `README.md`
- `.github/workflows/ci.yml`
- Issue #58: `CI infrastructure: GitHub Actions jobs fail before step creation`
- Draft PRs #121, #123, #124, #125, #129, #135, #137, #138, #141, #144, #145, #146, #147, #148, #151

## Source handling policy

- A URL alone is not evidence that a feature is enabled in this repository.
- Plan-dependent features must be checked in repository/account settings before rollout.
- Open Draft PR descriptions are current design evidence, not merged implementation authority.
- Every implementation PR records the exact source URLs, retrieval date, repository SHA and any unresolved discrepancy.
