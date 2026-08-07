# Browser GitHub capability matrix

Use this matrix only when translating the maintainer workflow into the tool names exposed by the current browser model. Confirm capabilities from live schemas or successful calls; product branding and repository roles are not proof of tool access.

For surface-level expectations, read `SURFACE_MATRIX.md`.

## Core operations

| Capability | Preferred operation | Acceptable fallback | Required evidence |
|---|---|---|---|
| Repository metadata | Get repository | Repository REST/MCP read | owner, visibility, default branch, permissions, merge settings |
| Latest `main` | Search or fetch commits | Fetch default-branch ref | full commit SHA and timestamp |
| File discovery | Repository code search | Tree or path listing | exact repository path and ref |
| File read | Fetch file by path and ref | Blob fetch | content, ref, blob SHA when available |
| PR inventory | Search or list PRs without diffs | Issue search filtered to PRs | number, state, Draft, refs, updated time, size |
| PR deep inspection | Fetch target PR and patch | PR metadata plus per-file patches | base SHA, head SHA, mergeability, exact changed paths |
| Issue inspection | Search or fetch Issues | Repository issue list | Issue number, state, labels, assignees, body |
| Review inspection | List reviews and thread-aware review threads | Flat comments with limitation recorded | review state and unresolved thread IDs |
| CI inspection | Fetch runs, jobs, steps, and logs | Authenticated `gh` Actions inspection | run ID, job ID, failed step, relevant log excerpt |
| Artifact inspection | List and download artifacts | Workflow summary marked incomplete | artifact ID, name, size, digest when available |
| Branch creation | Create branch from exact SHA | Non-force ref creation | branch and starting SHA |
| Single-file write | Create or update contents on branch | Edit tool on isolated branch | resulting commit SHA and re-fetched content |
| Multi-file write | Blob -> tree -> commit -> ref | Sequential contents commits | expected parent, resulting commit(s), changed paths |
| Draft PR creation | Create PR with `draft=true` | Create PR then convert to Draft | PR number, URL, base/head refs, Draft state |
| PR update | Update PR metadata | Comment with proposed metadata | re-fetched PR state |
| Failed-job rerun | Rerun failed jobs or named job | Governed new workflow run | run/job ID and new attempt |
| Ready conversion | Mark ready for review | None | `draft=false` after re-fetch |
| Merge | Squash merge with expected head SHA | Merge API with equivalent race guard | merged boolean and merge SHA |
| Post-merge check | Re-fetch PR, `main`, files, and checks | Separate API reads | merged state, `main` SHA, file evidence, workflow evidence |

## Governance and security operations

| Capability | Preferred operation | Acceptable fallback | Required evidence |
|---|---|---|---|
| Branch protection | Fetch protection or ruleset | Repository settings read | protected status and rule details |
| Rulesets | List repository rulesets | Settings screenshot or user-provided export | ruleset IDs, targets, enforcement state |
| Merge policy | Repository metadata | Settings read | squash/rebase/merge/auto-merge/update-branch flags |
| Actions permissions | Repository Actions settings | Workflow files plus limitation recorded | allowed actions and workflow token permissions |
| Dependabot | List Dependabot alerts | Security tab summary marked incomplete | alert IDs, severity, package, state |
| Code scanning | List code-scanning alerts | Security tab summary marked incomplete | alert IDs, rule, severity, state |
| Secret scanning | List secret-scanning alerts | Security tab summary marked incomplete | alert IDs and state without disclosing secret values |
| Dependency review | Dependency review or graph diff | Manifest and lockfile inspection | added/removed dependencies and risk |
| Projects | Project API or repository project list | Issue/PR labels as temporary fallback | project/item IDs, status, priority |
| Environments | Environment settings read | Workflow reference inspection | environment names and protection evidence |
| Webhooks and deploy keys | Settings API | Read-only settings export | identifiers and active state; never disclose secrets |
| Releases and packages | Release/package API | repository tags and workflow evidence | tag/version, assets or package status |

If the current connector exposes no operation for a row, report `TOOL_CAPABILITY_MISSING` or `NOT_VERIFIED`. Do not infer a secure state from the absence of returned alerts.

## Capability rules

1. Read access does not imply write, workflow, settings, security, or merge access.
2. Repository `admin`, `maintain`, or `push` metadata does not prove the current tool can perform every corresponding operation.
3. A browser model without Actions log access must not diagnose a code failure from a red check icon alone.
4. A job with zero steps is pre-run or infrastructure evidence, not a code failure.
5. A contents API update must use the current blob SHA when replacing an existing file.
6. Never update the same branch ref, PR, or file concurrently.
7. Never use a force option for routine remediation.
8. If expected-head merge is unavailable, re-fetch immediately before merge and record the weaker race guard. Stop for high-risk changes.
9. Security tools that return no data may mean “no findings” or “not authorized.” Distinguish these states explicitly.
10. Do not retrieve full patches, logs, and artifacts for every Open PR. Use lightweight inventory first, then deep-audit only the named or top-ranked candidates.

## Context-loading rules

Load only what the current task requires:

- Always: `SKILL.md`
- When tool mapping is unclear: `CAPABILITY_MATRIX.md`
- When platform behavior is unclear: `SURFACE_MATRIX.md`
- Human startup examples only: `INVOCATION_PROMPTS.md`

The executing Agent must not read `INVOCATION_PROMPTS.md` merely to perform a task.

## ChatGPT browser usage

A repository Skill is not guaranteed to be injected automatically into ChatGPT. Use `@GitHub` and explicitly fetch the exact default-branch paths before execution:

```text
@GitHub
First fetch and follow these files from the default branch of arumajirou/loto_forecast_platform:
.github/skills/browser-github-maintainer/SKILL.md
.github/skills/browser-github-maintainer/references/SURFACE_MATRIX.md

Then perform the requested repository maintenance using only live-confirmed capabilities.
```

A repository file cannot register a new ChatGPT `@mention`; the platform controls that UI.

## GitHub Copilot browser usage

After `.github/agents/github-maintainer.agent.md` is merged into the default branch, select **GitHub Maintainer** from the Copilot Agents selector. The Agent profile loads the project Skill and defers broad MCP tool definitions until needed where supported.

## Copilot CLI and IDE usage

Select **GitHub Maintainer** through the available Agent selector, or explicitly request the `browser-github-maintainer` Skill. Local `git`, `gh`, MCP, and execution capabilities still require live authentication and permission checks.