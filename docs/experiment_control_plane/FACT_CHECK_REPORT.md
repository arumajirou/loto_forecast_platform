# Fact-check Report

## Repository facts observed

- Repository is private and owned by a personal GitHub account.
- Default branch is `main`.
- Observed main head at package generation is recorded in the package metadata but must be
  re-fetched before every implementation branch.
- PR #139 is a Draft documentation foundation for generic GitHub features and explicitly states
  that Projects cannot replace Registry, Promotion, approval, or production state.
- PR #137 owns promotion subject/status taxonomy and performs no real approval or deployment.
- PR #140 owns durable lifecycle/outbox/fault design.
- PR #141 owns the common telemetry contract.
- Repository Actions currently has a known pre-step failure pattern tracked by Issue #58; a run with
  no created steps and no actionable logs is not a demonstrated code-test failure.

## Official GitHub capability findings

### Issue Forms

Issue Forms support typed YAML inputs, validation, default labels, and assignees. They remain an
intake mechanism. The submitted Issue can later be edited, so the formal plan is stored as reviewed
Git content.

Official references:

- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms
- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository

### Projects

GitHub Projects supports custom fields, built-in workflows, GraphQL, and Actions automation. A
Project can contain up to 50 fields. The Project is a projection of experiment state, not the
authoritative scientific evidence store.

Official reference:

- https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects

### Manual and external dispatch

A manually dispatchable workflow must use `workflow_dispatch` and the workflow file must exist on
the default branch. `repository_dispatch` also requires the receiving workflow file on the default
branch.

Official references:

- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

### Self-hosted runners

GitHub recommends ephemeral self-hosted runners for autoscaling; one job is assigned to an ephemeral
runner, which is then deregistered. Runner logs should be forwarded externally. Self-hosted runners
connect outbound to GitHub over HTTPS.

Official reference:

- https://docs.github.com/en/actions/reference/runners/self-hosted-runners

### Runner security

A compromised runner may expose secrets and the job token. Trigger type and token permissions
matter. Unknown or unreviewed code must never run in a privileged local runner lane.

Official reference:

- https://docs.github.com/en/actions/concepts/security/compromised-runners

### GitHub Apps and checks

GitHub App installation tokens are permission-scoped and expire after one hour. GitHub Apps can
create and update Check Runs. GitHub recommends GitHub App authentication instead of personal access
tokens for app automation.

Official references:

- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
- https://docs.github.com/en/rest/authentication/endpoints-available-for-github-app-installation-access-tokens
- https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/best-practices-for-creating-a-github-app

### Rulesets

Rulesets can require status checks and can restrict the accepted status source to a selected GitHub
App. Branch and tag rules are used for protected plan, result, and campaign identities.

Official reference:

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets

### Artifacts

Workflow artifacts and logs are temporary. Private repositories can configure retention between
one and 400 days, subject to account or organization limits. Permanent evidence therefore lives
outside Actions storage and is indexed by immutable hash.

Official reference:

- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository

### Personal-account permission limitation

A personal-account repository has owner and collaborator permission levels; private collaborators
receive write access. Organization repositories provide granular Read, Triage, Write, Maintain, and
Admin roles. Organization transfer is recommended before multi-user approval separation becomes a
formal requirement.

Official references:

- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository
- https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization

### Environments

Environment secrets and variables can gate jobs, but required-reviewer availability for a private
repository depends on the GitHub plan. The initial design therefore does not rely solely on
environment required reviewers.

Official reference:

- https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments

## Result

```text
CONTROL_PLANE_DESIGN=SUPPORTED
LONG_RUNNING_ACTION_JOB=REJECTED
PUBLIC_LOCAL_WEBHOOK=NOT_REQUIRED
GITHUB_APP=RECOMMENDED
EPHEMERAL_RUNNER=CONDITIONAL
PROJECT_AS_AUTHORITY=REJECTED
ACTIONS_ARTIFACT_AS_PERMANENT_STORE=REJECTED
PERSONAL_REPO_ROLE_SEPARATION=LIMITED
```
