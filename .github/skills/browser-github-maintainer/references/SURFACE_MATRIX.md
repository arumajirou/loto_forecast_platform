# Browser and agent surface matrix

This file describes expected capability patterns, not guaranteed permissions. The executing model must confirm live tool schemas or successful calls before writing, rerunning workflows, changing settings, or merging.

## Surface comparison

| Surface | How to invoke | Skill loading | Typical strengths | Capabilities that must not be assumed |
|---|---|---|---|---|
| ChatGPT with `@GitHub` | Select `@GitHub` and name the repository | Explicitly fetch the exact `.github/skills/browser-github-maintainer/SKILL.md` path; automatic repository Skill injection is not assumed | Structured repository, PR, review, file, Actions, and connector-backed write operations when exposed | Settings, rulesets, security alerts, workflow dispatch, write, rerun, and merge permissions |
| GitHub Copilot Chat on GitHub.com | Use Copilot Chat in repository context | Custom instructions and relevant repository capabilities may be available; explicitly name the Skill when needed | Repository-aware questions and GitHub operations with interactive authorization where supported | Unattended settings changes, protection bypass, unrestricted repository writes, and direct merge without current confirmation |
| GitHub Copilot cloud agent | Assign an Issue or task and select **GitHub Maintainer** | Agent profile is selected; it reads the project Skill | Checkout-based editing, command execution in the agent environment, commits, and PR creation | Broad GitHub MCP write access, repository settings, organization data, secrets, protected operations, and merge rights |
| GitHub Copilot CLI | Select **GitHub Maintainer** or name the Skill | Project Skills are discoverable; the Agent profile can defer MCP tools where supported | Local `git`, authenticated `gh`, command execution, repository MCP, testing, and PR workflows | Authentication, write scope, Actions log access, settings access, and merge rights without live checks |
| IDE Agent mode | Select the repository Agent when supported | Project Skill discovery varies by IDE and version | Local code edits, tests, source navigation, and configured MCP tools | GitHub write, workflow, security, and settings capabilities without configured authentication |
| Other browser model with GitHub connector | Select its GitHub integration | Explicitly fetch the Skill path | Depends on connector schema | Every write, rerun, security, settings, and merge capability until proven |

## Required surface report

At the start of a maintenance run, record:

```text
SURFACE=
AUTHENTICATION_STATUS=
REPOSITORY_SCOPE=
TOOLS_CONFIRMED=
TOOLS_MISSING=
PERMISSION_STATUS=
```

Do not copy a capability result from a previous session. Tokens, app installations, policies, repository settings, subscriptions, and tool schemas can change.

## Skill-loading policy

### ChatGPT and generic connectors

Fetch the exact default-branch path before execution:

```text
.github/skills/browser-github-maintainer/SKILL.md
```

Fetch `CAPABILITY_MATRIX.md` only when tool mapping is unclear. Fetch this `SURFACE_MATRIX.md` only when environment behavior is unclear.

### GitHub Copilot custom agent

The Agent profile at:

```text
.github/agents/github-maintainer.agent.md
```

instructs the selected Agent to read the Skill. The Agent must not load `INVOCATION_PROMPTS.md`; that file is only for users starting a session.

## Write and merge policy by evidence

A write or merge is allowed only when all are true:

1. the current surface exposes the required operation
2. repository and target permissions are confirmed
3. the target branch or PR head was re-fetched immediately before the operation
4. the operation does not write directly to `main`, force-update a ref, bypass protection, or weaken checks
5. the tool response proves the resulting commit, PR state, workflow attempt, or merge SHA

When an operation needs user approval in the interface, report:

```text
USER_APPROVAL_REQUIRED
```

Do not report the operation as completed before approval and a successful result are visible.

## Governance and security limitations

Repository metadata may expose merge flags but not full rulesets, branch protection, Actions permissions, security alerts, Projects, environments, webhooks, or deploy keys.

For every unavailable class, report one of:

```text
NOT_VERIFIED
TOOL_CAPABILITY_MISSING
INSUFFICIENT_PERMISSION
```

The absence of returned alerts is not evidence that scanning is enabled or that no findings exist.

## Efficiency policy

Broad `github/*` or MCP toolsets can be expensive to load. Where the surface supports deferred tool loading, enable it. Regardless of surface:

- inventory all PRs with lightweight metadata
- retrieve patches, review threads, logs, and artifacts only for the named target or top-ranked candidates
- process one write or merge target at a time
- avoid reading human invocation examples during execution
- reuse already fetched immutable evidence only within the same locked head SHA

## Official references

- GitHub custom agents configuration: `https://docs.github.com/en/copilot/reference/custom-agents-configuration`
- Agent Skills for Copilot: `https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills`
- Copilot CLI tool search and deferred loading: `https://docs.github.com/en/copilot/concepts/agents/copilot-cli/tool-search`

These references describe platform behavior but do not replace live capability discovery.