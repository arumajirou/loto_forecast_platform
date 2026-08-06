# Test Plan — GitHub Projects Governance v1

## Focused checks

```bash
python scripts/github_projects/governance.py \
  --spec configs/github_projects/governance_v1.yaml \
  validate

python scripts/github_projects/governance.py \
  --spec configs/github_projects/governance_v1.yaml \
  render-owner-plan --format json

python -m compileall -q scripts/github_projects tests/github_platform
pytest -q tests/github_platform/test_github_projects_governance.py
```

## Required assertions

- strict schema rejects unknown keys;
- fields and views are unique and complete;
- Status and Evidence Status remain separate;
- Project authority is exactly `governance_only`;
- one auto-add workflow targets the intended repository;
- generated owner commands request the `project` scope;
- no GitHub Actions workflow is generated as a silent substitute;
- rendered output contains no token, password, secret or callback value.

## Live acceptance

A live Project is verified only when:

1. Project identity, visibility and repository link are exported;
2. all fields and exact options are present;
3. all seven views exist with expected layout and filters;
4. declared built-in workflows are enabled;
5. a new Issue and Draft PR are added as expected;
6. closed Issue and merged PR transition to `Done`;
7. `FAILED`, `BLOCKED` and `PARTIALLY_VERIFIED` remain representable;
8. Project changes do not alter registry, promotion or production state;
9. JSON exports, screenshots, manifest and SHA-256 verify.

## Actions boundary

Issue #58 remains `ACTIONS_BLOCKED_PRE_RUN`. This increment does not add an Actions workflow, and no
zero-step rerun should be requested without an administrative change.
