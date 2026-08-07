# GitHub Actions pre-run blocker

## Status

`CI_BLOCKED_PRE_RUN / REPOSITORY_OR_ACCOUNT_INFRASTRUCTURE`

Canonical repository-wide issue: `#58` — **CI infrastructure: GitHub Actions jobs fail before step creation**

PR #48 dependency tracker: `#61` — **PR #48 CI dependency: repository-wide pre-run blocker tracked in #58**

This document records an external verification blocker for PR #48. It does not classify the
branch code as failing, and it does not count as passing CI evidence.

## Latest PR #48 reproduction

- Repository visibility: `private`
- Workflow: `.github/workflows/ci.yml`
- Workflow name: `ci`
- Runner label: `ubuntu-latest`
- Head: `a97b5f58367e423625678debf6c7b49d7eca6821`
- Run ID: `31001553962`
- Run number: `1869`
- Job ID: `92291396321`
- Job name: `test`
- Conclusion: `failure`
- Configured workflow steps: present
- Job steps returned by GitHub API: empty
- Job-log download: `404 BlobNotFound`
- Workflow artifacts: none
- Commit combined statuses: none
- Runner-execution evidence: absent

Independent PRs #55, #56, and #57 reproduce the same zero-step pattern. The blocker is therefore
not specific to PR #48, the reconciliation implementation, or a particular documentation head.

## Workflow definition check

The checked-in workflow is structurally populated and uses:

- `runs-on: ubuntu-latest`
- `actions/checkout@v6`
- `actions/setup-python@v6`
- Python 3.13
- CPU-only PyTorch installation
- editable project installation
- Ruff format and lint
- compileall
- repository pytest

An empty API step list does not mean the workflow file has no steps. It means no configured step
produced runner-execution evidence for the observed job.

## Classification

The strongest supported classification is:

`job failed before producing runner-execution evidence`

Because the repository is private and multiple independent PRs fail identically, the remaining
administrative classes are:

1. repository or account Actions disabled or restricted;
2. private-repository Actions minutes, storage, budget, billing, or payment restriction;
3. standard GitHub-hosted runners disabled by repository, organization, or account policy;
4. unavailable runner group, concurrency, or queue restriction;
5. GitHub-controlled repository/account disablement that normal settings cannot restore;
6. platform incident not represented in the jobs API.

The current connector cannot identify which class applies. Do not claim a specific root cause
without observing the repository/account UI or a GitHub Support response.

## Owner investigation order

In GitHub UI, inspect:

1. Repository **Settings → Actions → General**
   - Actions enabled;
   - GitHub-authored actions permitted;
   - standard GitHub-hosted runners permitted.
2. Account **Billing & plans → Metered usage / Budgets and alerts**
   - remaining Actions minutes and storage;
   - Actions budget and any stop-usage limit;
   - payment-method or billing restrictions.
3. Repository **Settings → Actions → Runners**
   - no unavailable runner-group requirement;
   - no hosted-runner policy restriction;
   - no persistent queue or concurrency restriction.
4. Failed run page
   - retain any billing, policy, account, or runner banner not exposed by the jobs API.
5. GitHub Support
   - required when the UI reports Actions disabled for the account or repository and normal
     settings cannot restore it.

After GitHub CLI is installed and authenticated with `repo` and `workflow` scopes, retain:

```bash
gh run view 31001553962 \
  --repo arumajirou/loto_forecast_platform

gh api \
  /repos/arumajirou/loto_forecast_platform/actions/jobs/92291396321
```

## Tracking policy

- Issue #58 is the canonical repository-wide blocker.
- Issue #61 records only PR #48's dependency on #58.
- Do not append another comment for every unchanged zero-step branch head.
- Add new evidence only after an external setting changes, GitHub exposes a new message, or a job
  reaches real workflow steps.
- Do not repeatedly rerun while steps and logs remain absent.
- Do not modify feature code without a concrete workflow error.

## Required resolution evidence

The repository-wide blocker is resolved only when a run has:

- at least one real workflow step;
- checkout and Python-setup records;
- accessible logs;
- Ruff and compileall results;
- pytest results;
- a final required-check conclusion.

A rerun that again returns zero steps, no log, and no artifacts does not add diagnostic value.

## PR #48 boundary

PR #48 remains Draft while it depends on issue #58. Restoring runner startup is necessary but not
sufficient: the PR also requires the exact-head local promotion gate, lock validation, focused
`95/0/0`, full pytest, installed `hierarchicalforecast==1.5.1`, runtime `40/40/40/0`, method
partition `24/16`, verified package publication, standalone verification, and all SHA-256 roots.
