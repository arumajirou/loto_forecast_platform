# Third-Party Audit Guide

This guide is for an independent reviewer who did not implement the integration.

## 1. Verify repository and pull request identity

Record the current values before reviewing:

```bash
gh repo view arumajirou/loto_forecast_platform \
  --json nameWithOwner,defaultBranchRef,url

gh pr view <INTEGRATION_PR_NUMBER> \
  --repo arumajirou/loto_forecast_platform \
  --json state,isDraft,mergeable,baseRefName,headRefName,headRefOid,url
```

Expected base branch: `main`

Expected head branch: `integration/consolidate-open-prs-20260805`

The PR must remain unmerged during review.

## 2. Confirm the frozen provenance

Review:

- `SUPERSESSION_MATRIX.json`
- `VERIFICATION_REPORT.md`
- the integration PR description
- the integration PR commit list

Check that these SHAs are consistent:

- audited `main`: `3dfc6481a0d83eb578f5c0ec4c776e324f7aef1d`
- PR #35 source: `03473ea869e91ea7253832e2900b0738bc769c71`
- pytest fix: `5af130e63c8f863e2cc79d53f5c9b890114f8cc5`

## 3. Inspect the diff first, not only the PR summary

```bash
gh pr diff <INTEGRATION_PR_NUMBER> \
  --repo arumajirou/loto_forecast_platform \
  > /tmp/loto-integration.diff

less /tmp/loto-integration.diff
```

The additional integration-specific product change should be limited to pytest collection isolation in `pyproject.toml`. Audit documents are expected under:

`docs/integration/open-pr-consolidation-20260805/`

The bulk of the feature diff should match PR #35.

Red flags:

- model IDs renamed or silently substituted
- metrics removed or primary metric changed away from Hit@±1
- future/actual values added to prospective payloads
- Holdout opened or rewritten
- raw data committed
- credentials, tokens, DSNs or private keys
- model binaries, caches or large generated artifacts
- force-push or direct commits to `main`

## 4. Verify supersession decisions independently

### PR #21

Open PR #21 and merged PR #34. Confirm PR #34 explicitly says it ports PR #21 onto current `main`, then inspect the 35 TCN paths in current `main`.

### PR #20

Confirm PR #20 describes formatting only and is based on an old `main`. Confirm the integration CI passes the repository Ruff checks without applying PR #20.

### PR #13

Compare the following paths between PR #13 head and current `main` using GitHub file history or `git rev-parse <ref>:<path>`:

```text
scripts/tsfm/run_granite_ttm_runtime_probe.py
environments/granite-ttm/pyproject.toml
environments/granite-ttm/run-python.sh
environments/granite-ttm/uv.lock
tests/test_granite_ttm_runtime_probe.py
```

Expected blob SHAs are listed in `VERIFICATION_REPORT.md`. Then review merged PRs #15 and #16 for the later complete TSFM certification evidence.

## 5. Verify CI on the final PR head

Do not accept screenshots alone. Open the workflow run attached to the final PR head SHA.

Confirm these steps are green:

- Ruff format
- Ruff lint
- compileall
- full pytest

Inspect the pytest log and confirm the previous collection errors for `test_contracts`, `test_metrics` and `test_registry` are absent.

```bash
HEAD_SHA="$(gh pr view <INTEGRATION_PR_NUMBER> \
  --repo arumajirou/loto_forecast_platform \
  --json headRefOid --jq .headRefOid)"

gh run list \
  --repo arumajirou/loto_forecast_platform \
  --commit "$HEAD_SHA" \
  --limit 10
```

## 6. Check unresolved reviews and merge state

```bash
gh pr checks <INTEGRATION_PR_NUMBER> \
  --repo arumajirou/loto_forecast_platform

gh pr view <INTEGRATION_PR_NUMBER> \
  --repo arumajirou/loto_forecast_platform \
  --json state,isDraft,mergeable,reviewDecision,statusCheckRollup
```

Required review outcome before merge:

- open
- not draft
- mergeable
- all checks successful
- no unresolved review thread
- no auto-merge

## 7. Time-series semantic audit

Review the relevant tests and implementation for:

- strict chronological folds
- fold-local fit of transforms and tuning
- no target/future leakage
- OOF separation from Holdout and Prospective
- seed-level results plus mean, variance and worst value
- explicit baselines under the same folds
- prospective prediction sealing before actual disclosure
- model/backend identity persistence
- fail-closed behavior for unavailable or unsupported runtimes

A green CI run is not sufficient evidence of prediction accuracy or GPU certification.

## 8. Recommended final verdict format

```text
AUDIT_STATUS=PASS|PARTIAL|FAIL
PR_NUMBER=
HEAD_SHA=
CI_RUN=
DIFF_REVIEW=PASS|FAIL
SUPERSESSION_PR13=PASS|PARTIAL|FAIL
SUPERSESSION_PR20=PASS|PARTIAL|FAIL
SUPERSESSION_PR21=PASS|PARTIAL|FAIL
PYTEST_COLLECTION=PASS|FAIL
FULL_PYTEST=PASS|FAIL
SECRET_SCAN=PASS|FAIL
LARGE_FILE_SCAN=PASS|FAIL
TIME_SERIES_CONTRACT_REVIEW=PASS|PARTIAL|FAIL
MERGE_RECOMMENDATION=APPROVE|HOLD|REJECT
NOTES=
```
