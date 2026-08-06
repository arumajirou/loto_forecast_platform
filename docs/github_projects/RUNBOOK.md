# Runbook — GitHub Projects Governance v1

## Daily operation

- use Project fields to summarize Issue and PR governance state;
- keep Evidence Status independent from lifecycle Status;
- retain Run IDs, SHAs and evidence in Issues, PRs or artifacts;
- never infer model promotion or production state from a Project card.

## Failure handling

### Item is missing

Confirm the auto-add workflow is enabled and the item matches its supported filter. Auto-add does
not backfill existing matching items. Add a missing existing item with `gh project item-add`.

### Status is incorrect

Correct the field without deleting comments, PR evidence or failed Run IDs. A card movement must not
rewrite historical evidence.

### Workflow is disabled

Record the workflow export and screenshot, re-enable it through the Project UI, and verify one new
test item. Do not claim recovery from the UI toggle alone.

### Permissions fail

Run `gh auth status`, refresh the `project` scope, verify Project ownership and record the exact 403
or 404. Do not use a broader token than required.

## Rollback

1. Export Project, fields, items, views and workflows.
2. Disable built-in workflows.
3. Unlink the Project from the repository if required.
4. Close the Project rather than deleting it during initial rollback.
5. Verify repository Issues and PRs remain intact.
6. Delete only after explicit owner approval and retained export evidence.

Removing repository specification files does not delete a live Project. Live Project rollback and
repository-code rollback are separate operations.
