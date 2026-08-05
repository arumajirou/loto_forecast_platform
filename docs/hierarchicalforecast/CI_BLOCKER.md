# GitHub Actions runner-start blocker

## Status

`BLOCKED_RUNNER_START`

Tracking issue: `#61` — **CI blocker: GitHub Actions jobs fail before runner execution**

This document records an external verification blocker for PR #48. It does not classify the
branch code as failing, and it does not count as passing CI evidence.

## Latest observed run

- Workflow: `.github/workflows/ci.yml`
- Workflow name: `ci`
- Head: `616b3d330b063338382194d31b9780d955bd2ca6`
- Run ID: `30985512951`
- Run number: `1033`
- Job ID: `92239226331`
- Job name: `test`
- Conclusion: `failure`
- Job steps returned by GitHub API: empty
- Downloadable job log: absent
- Workflow artifacts: none observed
- Runner-execution evidence: absent

The latest commit adds documentation only. The repeated zero-step result therefore adds evidence
that the external runner-start blocker is independent of the HierarchicalForecast implementation
code path.

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

The API returning no job steps therefore does not mean that the workflow file contains no
steps. It means no configured step produced execution evidence for the observed job.

## Classification

The available evidence supports only:

`job failed before producing runner-execution evidence`

The exact administrative cause is not observable through the current connector. Do not claim a
specific root cause without checking repository/account settings.

Possible external classes to inspect include:

1. repository or account Actions disabled or restricted
2. standard GitHub-hosted runners disabled by policy
3. private-repository Actions minutes, budget, billing, or payment restriction
4. account or organization concurrency/queue restriction
5. GitHub-hosted runner service incident or account-level disablement

## Owner checklist

In GitHub UI, inspect:

1. Repository **Settings → Actions → General**
   - Actions enabled
   - GitHub-authored actions permitted
   - standard GitHub-hosted runners permitted
2. Account or organization billing and Actions usage
   - remaining included minutes
   - Actions budget/spending limit
   - valid payment method when required
3. **Settings → Actions → Runners** and current jobs
   - no policy requiring unavailable runner groups
   - no concurrency saturation or persistent queue
4. GitHub Status and repository Actions page
   - no platform incident
   - read any run-level banner or billing/policy message not exposed by the API

Record findings and resolution evidence in issue #61.

## Required resolution evidence

The blocker is resolved only when a run for the current branch head has:

- at least one real job step
- checkout/install logs
- Ruff and compileall results
- pytest results
- final required-check conclusion

A rerun that again returns zero steps, no log, and no artifacts does not add diagnostic value.
Do not repeatedly rerun without changing the external condition or obtaining new evidence.

## PR #48 boundary

PR #48 must remain Draft while issue #61 is open. Even after runner startup is restored, the PR
also requires the real installed `hierarchicalforecast==1.5.1` 40-case certification and verified
evidence ZIP before it can be marked ready for review.
