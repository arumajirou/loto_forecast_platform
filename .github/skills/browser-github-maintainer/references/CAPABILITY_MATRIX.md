# Browser GitHub capability matrix

Use this matrix to translate the maintainer workflow into whatever tool names the current browser model exposes. Confirm capabilities from live tool schemas or successful calls; do not infer them from product branding alone.

| Capability | Preferred operation | Acceptable fallback | Required evidence |
|---|---|---|---|
| Repository metadata | Get repository | Repository REST/MCP read | owner, default branch, permissions, merge settings |
| Latest `main` | Search/fetch commits | Fetch default-branch ref | full commit SHA and timestamp |
| File discovery | Repository code search | Tree/path listing | exact repository path |
| File read | Fetch file by path/ref | Blob fetch | content, ref, blob SHA when available |
| PR discovery | Search/list PRs | Issue search filtered to PRs | number, state, draft, base/head refs |
| PR inspection | Fetch PR | PR metadata plus patch calls | base SHA, head SHA, mergeability, changed files |
| Review inspection | List reviews and review threads | Flat comments with limitation recorded | review state and unresolved thread IDs |
| CI inspection | Fetch runs/jobs/steps/logs | `gh` Actions inspection | run ID, job ID, failed step, log excerpt |
| Artifact inspection | List/download artifacts | Workflow summary only, marked incomplete | artifact ID, name, digest when available |
| Branch creation | Create branch from exact SHA | Non-force ref creation | branch and starting SHA |
| Single-file write | Create/update contents on branch | Edit tool on isolated branch | resulting commit SHA and file content |
| Multi-file write | Blob -> tree -> commit -> ref | Sequential contents commits | parent SHA, resulting commit(s), changed paths |
| Draft PR creation | Create PR with `draft=true` | Create PR then convert to Draft | PR number, URL, base/head refs, draft state |
| PR update | Update PR metadata | Comment with proposed metadata | resulting PR state |
| Rerun failure | Rerun failed jobs/job | New governed workflow dispatch | run/job ID and new attempt |
| Ready conversion | Mark ready for review | None | `draft=false` after re-fetch |
| Merge | Squash merge with expected head SHA | Merge API with an equivalent head lock | merged boolean and merge SHA |
| Post-merge check | Re-fetch PR, `main`, files, checks | Separate API reads | merged state, `main` SHA, file evidence |

## Capability rules

1. Connector or MCP read access does not imply write access.
2. Repository `admin` or `push` metadata does not prove the current tool can perform every write; verify the operation schema or a successful call.
3. A browser model without Actions log access must not diagnose a test root cause from the red check icon alone.
4. A contents API update must use the current blob SHA when replacing an existing file.
5. Never update the same branch ref or file concurrently.
6. Never use a force option for routine remediation.
7. If expected-head merge is unavailable, re-fetch the PR immediately before merge and record that the weaker race guard was used. For protected or high-risk changes, stop instead.

## ChatGPT browser usage

In ChatGPT, `@GitHub` is the connected application selector. Use prompts such as:

```text
@GitHub Use the browser-github-maintainer skill in arumajirou/loto_forecast_platform. Re-fetch current state, complete every safe operation supported by the connector, and report exact blockers.
```

A repository file cannot register a new ChatGPT `@mention`; the platform controls that UI.

## GitHub Copilot browser usage

After `.github/agents/github-maintainer.agent.md` is merged into the default branch, select **GitHub Maintainer** from the Copilot agents dropdown on GitHub.com. The agent profile explicitly loads this project skill.

## Copilot CLI usage

Use `/agent` to select **GitHub Maintainer**, or explicitly prompt:

```text
Use the /browser-github-maintainer skill to audit and safely process the next PR.
```
