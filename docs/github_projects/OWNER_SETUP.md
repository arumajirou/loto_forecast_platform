# Owner Setup — GitHub Projects Governance v1

## Prerequisites

Install GitHub CLI, authenticate, and add the minimum `project` scope:

```bash
gh auth status
gh auth refresh -s project
```

The repository connector used to prepare this PR cannot create or inspect Projects. The commands
below are owner-run actions, not executed evidence.

## Validate and render the plan

```bash
python scripts/github_projects/governance.py \
  --spec configs/github_projects/governance_v1.yaml \
  validate

python scripts/github_projects/governance.py \
  --spec configs/github_projects/governance_v1.yaml \
  render-owner-plan \
  --format markdown \
  > owner-project-plan.md
```

Review the generated plan before running any mutating command.

## Project creation

```bash
gh project create \
  --owner arumajirou \
  --title "Loto Forecast Platform Governance" \
  --format json
```

Record the returned Project number and node ID. Link the Project to the repository:

```bash
gh project link <PROJECT_NUMBER> \
  --owner arumajirou \
  --repo loto_forecast_platform
```

## Fields

Use the generated plan to create custom fields. The built-in `Status` field already exists and must
be edited in the Project UI to exactly these options:

```text
Intake
Spec
Design
Ready
In Progress
Verification
Blocked
Failed
Done
```

Do not delete a populated field or change option identity after use without an export and migration
plan.

## Views

The generated plan contains REST commands for user-owned Project views. Resolve the numeric user ID:

```bash
gh api /users/arumajirou --jq .id
```

Create each view only after the Project number and user ID are verified. Current official REST
endpoints use API version `2026-03-10`. Retain every response as JSON.

## Built-in workflows

Configure these through Project → menu → Workflows:

1. auto-add open Issues and pull requests from `arumajirou/loto_forecast_platform`;
2. added item → `Intake`;
3. closed Issue → `Done`;
4. merged pull request → `Done`.

The design uses one auto-add workflow, which stays within the documented GitHub Free limit. Existing
matching items are not backfilled automatically by auto-add; add them explicitly if required.

## Manual policies

The following are not claimed as built-in automation:

- `blocked` label → Status `Blocked`;
- Draft PR → PR Phase `Draft`, Status `In Progress`;
- verification failure → Status `Failed`, Evidence Status `FAILED`.

Apply these manually until a separately reviewed API or webhook automation is implemented.

## Evidence export

Retain these files under a non-secret evidence directory:

```text
PROJECT.json
PROJECT_FIELDS.json
PROJECT_ITEMS.json
PROJECT_VIEWS.json
PROJECT_WORKFLOWS.json
ARTIFACT_MANIFEST.json
SHA256SUMS
SCREENSHOTS/
```

Suggested read-only exports:

```bash
gh project view <PROJECT_NUMBER> --owner arumajirou --format json > PROJECT.json
gh project field-list <PROJECT_NUMBER> --owner arumajirou --format json \
  > PROJECT_FIELDS.json
gh project item-list <PROJECT_NUMBER> --owner arumajirou --limit 500 \
  --format json > PROJECT_ITEMS.json
```

Use the REST views endpoint and GraphQL `ProjectV2.workflows` connection for views and workflows.
Do not export tokens, authorization headers or unnecessary private node IDs.
