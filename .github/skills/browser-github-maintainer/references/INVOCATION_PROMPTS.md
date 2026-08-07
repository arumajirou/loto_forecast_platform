# Invocation prompts

These prompts are written for browser-based models. Replace the target only when necessary.

## 1. Full maintainer loop

```text
@GitHub
Use the browser-github-maintainer skill for:
https://github.com/arumajirou/loto_forecast_platform

Re-fetch the latest main SHA, all Open and Draft PRs, related Issues, reviews, unresolved review threads, changed files, mergeability, and GitHub Actions evidence.

Select the highest-priority safe target, produce a compact execution plan, then perform every supported operation in the current session: branch or PR remediation, repository file edits, commit, PR update, CI inspection, failed-job rerun, merge-gate evaluation, SHA-locked squash merge, and post-merge verification.

Do not require terminal operation from me. Do not force-push, write directly to main, bypass protections, expose secrets, or merge without current evidence. Process one merge target at a time and report exact identifiers and blockers.
```

## 2. Named PR remediation and merge

```text
@GitHub
Use the browser-github-maintainer skill for PR #<NUMBER> in arumajirou/loto_forecast_platform.

Re-fetch the PR and main. Inspect the full patch, overlapping PRs, review state, unresolved threads, workflow runs, jobs, steps, and logs. Diagnose the first root cause before editing. Apply only an in-scope minimal fix to the PR branch, verify it, re-check the head SHA, and squash-merge only when every merge gate passes. Verify main after merge.
```

## 3. Directory redesign and implementation

```text
@GitHub
Use the browser-github-maintainer skill to redesign and implement changes under `<DIRECTORY>` in arumajirou/loto_forecast_platform.

First inspect the directory recursively, its callers, tests, configs, documentation, related PRs and Issues, and ownership boundaries. Create Specification, Basic Design, Detailed Design, task order, test plan, rollback plan, and stop conditions. Then implement on a new Draft PR from the latest main, using the available GitHub repository-write capabilities. Keep unrelated files out of scope and verify focused tests before broad tests.
```

## 4. CI root-cause analysis

```text
@GitHub
Use the browser-github-maintainer skill to investigate failing checks for PR #<NUMBER>.

Retrieve run, job, step, and log evidence. Distinguish code failure, test failure, lint/type failure, dependency failure, workflow failure, runner failure, pre-run billing block, flaky failure, and unrelated-main failure. Do not patch until the root cause is supported. Apply the smallest fix, rerun only the failed job when possible, and stop after three unsuccessful remediation loops.
```

## 5. Read-only audit

```text
@GitHub
Use the browser-github-maintainer skill in read-only mode for arumajirou/loto_forecast_platform.

Audit repository permissions and merge settings, main, Open PRs, Issues, branches, overlapping changes, reviews, Actions, security-related evidence available to the connector, and dependency relationships. Make no writes. Return a prioritized queue with exact PR numbers, SHA values, risks, blockers, and recommended next operations.
```

## 6. GitHub Copilot browser agent

After the agent profile is merged into `main`:

1. Open GitHub Copilot Agents on GitHub.com.
2. Select repository `arumajirou/loto_forecast_platform`.
3. Select **GitHub Maintainer** from the agent dropdown.
4. Use a direct request such as:

```text
Audit the current Open PR queue and safely complete the highest-priority merge target. Follow the browser-github-maintainer skill and perform all supported operations without requesting user terminal access.
```

## Interpretation of `@`

- ChatGPT browser: `@GitHub` selects the installed GitHub application. The project skill name must also be stated in the prompt.
- GitHub Copilot browser: the custom agent is selected from the agents dropdown after its profile is merged into the default branch.
- Copilot CLI: select the agent with `/agent`; skills can be named with `/browser-github-maintainer` in the prompt.
