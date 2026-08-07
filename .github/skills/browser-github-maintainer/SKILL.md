---
name: browser-github-maintainer
description: Use when a browser-based AI model is asked to inspect, plan, modify, validate, review, or safely merge work in this repository through @GitHub, GitHub MCP, or GitHub Copilot without relying on user terminal access. Covers repository and directory audits, PR triage, branch and file changes, CI root-cause analysis, review resolution, SHA-locked squash merges, and post-merge verification.
license: Repository internal
---

# Browser GitHub Maintainer

## Purpose

Operate `arumajirou/loto_forecast_platform` from a browser-based AI session by using the connected GitHub application, GitHub MCP tools, Copilot cloud-agent tools, or equivalent repository APIs.

The user should not be required to run terminal commands. Use browser-accessible GitHub capabilities first. Ask for device or terminal action only when a required capability is unavailable and no safe API-based alternative exists.

This skill does not create a new ChatGPT application mention. In ChatGPT, `@GitHub` selects the GitHub app. In GitHub Copilot on GitHub.com, select the repository custom agent named `GitHub Maintainer`. In Copilot CLI, explicitly request `/browser-github-maintainer` or select the custom agent.

## Non-negotiable principles

- Re-fetch current state; never trust stale conversation state for a write or merge.
- Show evidence from tool results; never report an operation as complete without confirmation.
- No direct writes to `main`.
- No force-push.
- No branch-protection or ruleset bypass.
- No weakening or deleting required checks to manufacture a green result.
- No secret, token, credential, deploy-key, webhook-secret, or private callback disclosure.
- No unrelated changes in the same PR.
- One merge at a time.
- Squash merge with `expected_head_sha` or the closest available head-lock mechanism.
- Verify `main` after merge.
- Treat unavailable evidence as unavailable, not as PASS.

## 1. Capability discovery

At the start of every session, identify which capabilities actually exist. Tool names vary by browser model, so discover by capability rather than assuming an exact name.

Required capability groups:

1. Repository reads
   - repository metadata and permissions
   - default branch and merge settings
   - file search and file fetch
   - branch and commit lookup
2. PR and Issue reads
   - open/closed/draft PRs
   - changed files and patches
   - reviews and unresolved review threads
   - comments, labels, assignees, dependencies
3. Write operations
   - create branch
   - create/update/delete file on a non-default branch
   - create blob/tree/commit and update a ref, when available
   - create or update Draft PRs
4. Actions evidence
   - workflow runs
   - jobs and steps
   - failed job logs
   - artifacts
   - rerun failed jobs or a specific job
5. Merge operations
   - mark ready for review
   - merge with squash
   - expected head SHA validation
6. Post-merge reads
   - merged PR state
   - merge SHA
   - latest `main` SHA
   - resulting files and workflow state

Record confirmed and missing capabilities as:

```text
TOOLS_CONFIRMED=
TOOLS_MISSING=
PERMISSION_STATUS=
```

If a write capability is missing, continue with read-only audit, an exact patch plan, and a stop reason of `INSUFFICIENT_PERMISSION`. Do not pretend to have pushed or merged.

See `references/CAPABILITY_MATRIX.md` for the capability-to-tool mapping.

## 2. Initial audit

Before selecting or modifying work, re-fetch:

- repository owner, visibility, default branch, permissions, and merge settings
- latest `main` commit SHA
- open PRs and Draft PRs
- open Issues relevant to the requested work
- remote branches related to the work
- duplicate or superseded PRs and Issues
- target PR base branch, base SHA, head branch, head SHA, mergeability, commits, changed files, additions, and deletions
- review submissions and unresolved review threads
- combined status and relevant Actions runs, jobs, steps, logs, and artifacts
- overlapping changed files across open PRs

Create a run identifier:

```text
ghmaint-YYYYMMDD-HHMMSS-prNNN
```

Lock the snapshot in the report:

```text
RUN_ID=
MAIN_SHA=
BASE_SHA=
HEAD_SHA=
```

## 3. Work selection

Unless the user names a target, rank work as follows:

1. P0: fixes for broken `main`, CI, security, or repository governance
2. P1: foundations blocking multiple PRs
3. P2: small mergeable fixes with focused verification
4. P3: PRs with actionable review feedback
5. P4: merge conflicts or stale branches
6. P5: large feature PRs
7. P6: documentation and research-only changes

Within a priority, prefer fewer dependencies, smaller diffs, clearer verification, lower risk, and older work.

Process one merge target at a time. Parallelize only independent reads. Never perform parallel writes to the same branch, ref, PR, or file.

## 4. Risk classification

Classify the target before editing:

- `DOC_ONLY`
- `TEST_ONLY`
- `LOW_RISK_CODE`
- `NORMAL_CODE`
- `CI_OR_BUILD`
- `DATA_CONTRACT`
- `SCHEMA_OR_MIGRATION`
- `SECURITY`
- `PRODUCTION_CRITICAL`

`SCHEMA_OR_MIGRATION`, `SECURITY`, and `PRODUCTION_CRITICAL` require explicit rollback evidence and must stop when validation cannot be completed.

## 5. Plan before modification

Produce a compact execution record before the first write:

```text
OBJECTIVE=
ROOT_CAUSE=
CHANGE_SCOPE=
OUT_OF_SCOPE=
DEPENDENCIES=
FILES=
VERIFICATION=
ROLLBACK=
RISKS=
COMPLETION_CRITERIA=
STOP_CONDITIONS=
```

For broad work, follow:

`Specification -> Clarification -> Plan -> Tasks -> Implement -> Review -> Verify -> Merge`

Do not ask the user to confirm routine, already-authorized repository maintenance. Stop only for a material ambiguity, safety boundary, missing permission, or irreversible decision.

## 6. Branch and change procedure

### Existing PR

- Re-fetch the PR head SHA immediately before writing.
- Confirm the branch belongs to the repository and can be updated safely.
- Confirm the requested fix belongs to the PR scope.
- If the fix is unrelated, create a separate branch and Draft PR.

### New work

- Start from the latest `main` SHA.
- Use `agent/<purpose>-vN`, `feat/<purpose>-vN`, or `fix/<purpose>-vN`.
- Create a Draft PR by default.

### Remote API writes

Prefer an atomic multi-file commit when blob/tree/commit/ref capabilities are available:

1. fetch parent commit and base tree
2. create blobs
3. create one tree
4. create one commit with the expected parent
5. update the branch ref without force
6. re-fetch and verify the commit and file contents

When only contents API file writes are available, make sequential commits on the isolated branch and verify the branch after every write. Never leave a partially modified default branch.

## 7. Review and failure remediation

### Review feedback

Fetch both review submissions and thread-aware unresolved review threads. Classify each item as:

- actionable code change
- documentation request
- question requiring a reply
- resolved
- outdated
- duplicate
- conflicting feedback

Map each implemented change to the relevant thread. Resolve only threads with evidence that the requested change is complete. Do not self-approve your own work as independent review.

### CI failures

Before editing, obtain run, job, step, and log evidence. Classify the failure:

- `CODE_FAILURE`
- `TEST_FAILURE`
- `LINT_FAILURE`
- `TYPE_FAILURE`
- `DEPENDENCY_FAILURE`
- `WORKFLOW_FAILURE`
- `RUNNER_FAILURE`
- `BILLING_BLOCKED_PRE_RUN`
- `EXTERNAL_CHECK`
- `FLAKY`
- `UNRELATED_MAIN_FAILURE`

Use the loop:

`failure evidence -> root cause -> minimum patch -> focused verification -> commit -> rerun failed job -> re-fetch status`

Maximum remediation loops: 3. If the same root cause remains, stop with `REMEDIATION_EXHAUSTED`.

A job with zero executed steps is not evidence of a code or test failure. Record it as a pre-run or infrastructure block.

## 8. Verification order

Use the repository's `uv`, `pyproject.toml`, `uv.lock`, `src`, and `tests` conventions.

Run or obtain evidence in this order:

1. syntax or compile check for changed files
2. Ruff format for changed files
3. Ruff lint for changed files
4. mypy for the affected package
5. focused pytest
6. smoke test
7. related integration tests
8. full pytest
9. required GitHub checks

Do not begin with the heaviest suite. Do not claim a model or runtime works because it imports, registers, or reports itself as available. Verify load, input, inference, output shape, finite values, device, GPU process, VRAM, and CPU fallback when relevant.

## 9. Forecasting-specific safeguards

For data, features, training, evaluation, retraining, prediction lock, or monitoring changes, verify:

- chronological `Train -> Validation -> Holdout -> Prospective` boundaries
- scaler, encoder, feature selection, and tuning fitted only within Train
- no future information, duplicate rows, missing values, or ordering violations
- immutable raw data
- OOF evidence and multiple seeds with mean, variance, and worst result
- no selection based only on the best seed
- SHA-256 and timestamp locking of predictions before actuals are known
- fair comparison of univariate, exogenous, per-position, shared, and ensemble models

Report at minimum:

- Hit@±1 as the primary metric
- MAE, MSE, RMSE
- per-position Hit@±1
- all-position Hit@±1
- Random, constant, mean, median, last-value, frequency, and statistical-model baselines

## 10. Merge gate

Do not merge until all applicable items pass:

- PR state is open
- base branch is `main`
- PR is not Draft
- mergeable is true
- current head SHA equals the verified head SHA
- current base SHA has been re-fetched
- changed-file scope is expected
- no unresolved `REQUEST_CHANGES`
- no unresolved actionable review thread
- focused tests pass
- smoke test passes
- required checks pass or an explicitly governed equivalent evidence path exists
- no critical security finding
- no secret exposure
- rollback is possible

Immediately before merge:

1. re-fetch PR metadata
2. compare current head SHA with the verified SHA
3. re-fetch checks and reviews
4. mark ready only if the gate passes
5. squash merge with the verified expected head SHA

If the head moved, stop with `HEAD_MOVED` and restart the audit.

## 11. Post-merge verification

After a successful merge response, verify:

- PR `merged=true`
- merge commit SHA
- latest `main` SHA
- expected files and contents on `main`
- `main` workflow state
- no new regression failure attributable to the merge
- linked Issue state
- mergeability and base drift of dependent PRs

Do not directly repair `main`. Create a revert or hotfix Draft PR when a regression is found.

## 12. Stop conditions

Stop without merging when any of these applies:

- `SECURITY_REVIEW_REQUIRED`
- `DATA_LOSS_RISK`
- `MIGRATION_UNSAFE`
- `MERGE_CONFLICT`
- `HEAD_MOVED`
- `REMEDIATION_EXHAUSTED`
- `CI_BLOCKED_WITHOUT_ALTERNATIVE_EVIDENCE`
- `REQUIRED_CHECK_FAILED`
- `UNRESOLVED_REQUEST_CHANGES`
- `UNRELATED_CHANGES`
- `INSUFFICIENT_PERMISSION`
- `TOOL_CAPABILITY_MISSING`

Even when stopped, complete all safe audit, patch, Draft PR, Issue, or evidence-comment work supported by the tools.

## 13. Required final report

```text
RUN_ID=
TARGET_PR=
TARGET_ISSUE=
MAIN_SHA=
BASE_SHA=
HEAD_SHA=
RISK_CLASS=
TOOLS_CONFIRMED=
TOOLS_MISSING=
FILES_CHANGED=
PATCH_STATUS=
FOCUSED_TESTS=
SMOKE_TEST=
FULL_TEST=
CI_STATUS=
REVIEW_STATUS=
SECURITY_STATUS=
MERGE_GATE=
MERGED=
MERGE_SHA=
POST_MERGE_VERIFY=
NEXT_ACTION=
STOP_REASON=
```

Do not finish with a vague statement such as “ready” or “looks good.” Give exact identifiers, evidence, and the next executable action.