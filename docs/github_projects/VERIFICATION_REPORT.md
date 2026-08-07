# Verification Report — GitHub Projects Governance v1

## Status

`PARTIALLY_VERIFIED / DECLARATIVE_SPEC_EXECUTED / LIVE_PROJECT_NOT_CREATED`

## Verified

- repository is private, personal-account-owned and accessible with admin permission;
- default branch and base SHA were rechecked before branch creation;
- PR #139 remains Open, Draft and unmerged and was used read-only with owner authorization;
- no same-name implementation branch existed;
- no same-purpose implementation PR or exact ProjectV2 repository tooling was found;
- the connected GitHub tool has no Projects mutation or inspection functions;
- `gh` CLI is absent from the execution environment;
- current official GitHub documentation and CLI manuals were reviewed.

## Official facts applied

- GitHub CLI Project commands require the `project` token scope;
- `gh project create`, `field-create`, `link`, `view`, `field-list` and `item-list` are available;
- Projects support built-in workflows and automatic item addition;
- auto-add adds new or updated matching items and does not backfill existing matches;
- GitHub Free permits one auto-add workflow, while higher plans permit more;
- user-owned Project views have a current REST create-view endpoint;
- Project workflows can be inspected through the GraphQL `ProjectV2.workflows` connection;
- workflow objects expose name, number, enabled state and timestamps.

## Not executed

- live Project creation;
- field or view creation;
- built-in workflow configuration;
- Project item backfill;
- screenshots or live exports;
- Project permission verification through a `project`-scoped token;
- repository-native Ruff, mypy or full pytest;
- GitHub Actions.

These are `OWNER_UI_OR_API_ACTION_REQUIRED` or `EXECUTION_PENDING`, not PASS.

## Authority boundary

- model registry changed: NO
- promotion or approval changed: NO
- canary or production binding changed: NO
- evaluation or prediction-lock evidence changed: NO
- Holdout or Prospective opened or published: NO
- secret or Project token committed: NO
