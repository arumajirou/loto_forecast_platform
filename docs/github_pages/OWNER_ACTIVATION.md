# Owner Activation Gate — GitHub Pages

## Current result

`OWNER_UI_OR_API_ACTION_REQUIRED`

The repository is private and owned by a personal account. GitHub Pages availability for a private
repository depends on the GitHub plan. Pages sites are publicly available on the internet even when
the source repository is private unless an eligible enterprise access-control configuration applies.

## Required owner decisions

Record all of the following before a deployment PR:

```text
GITHUB_PLAN=<verified value>
PRIVATE_REPOSITORY_PAGES_ELIGIBLE=<true|false>
RESULTING_SITE_VISIBILITY=<public|private-enterprise-only|not-eligible>
PUBLICATION_APPROVED=<true|false>
APPROVER=<GitHub login>
APPROVED_AT_UTC=<timestamp>
```

For this personal-account repository, do not infer private site access from private repository
visibility.

## Required Settings checks

1. Repository → Settings → Pages:
   - confirm whether Pages is available;
   - do not select a source yet;
   - retain a screenshot excluding sensitive browser or account data.
2. Repository → Settings → Actions → General:
   - confirm Actions and GitHub-owned actions are allowed.
3. Account → Billing & plans:
   - confirm the plan and Actions usage/budget status.
4. Issue #58:
   - close only after a hosted job creates real steps and accessible logs.

## Separate deployment PR

Only after all gates pass, create a new branch from the then-current `main`. The deployment PR may
add a custom workflow using current pinned Pages actions, an audited build artifact, least-privilege
permissions, a `github-pages` environment, concurrency control, and a post-deploy smoke check.
