# GitHub Projects Governance v1

## Status

`PROCEED_LOCAL_ONLY / DECLARATIVE_SPEC_EXECUTED / PROJECT_CREATION_PENDING`

This package defines a reproducible GitHub Projects governance model for Issues and pull requests.
It does not create or modify a live Project because the connected GitHub tool has no Projects
mutation surface and the execution environment has no authenticated `gh` CLI.

## Scope

- declarative Project identity, fields, views, workflows and manual policies;
- strict Pydantic validation with `extra="forbid"`;
- deterministic owner execution plan generation;
- focused tests and rollback instructions;
- evidence export and screenshot requirements.

The Project is governance metadata only. It is not authoritative for model registry, promotion,
approval, prediction locking, Holdout, Prospective, canary or production binding.

## Files

- `configs/github_projects/governance_v1.yaml`
- `scripts/github_projects/governance.py`
- `tests/github_platform/test_github_projects_governance.py`
- `docs/github_projects/OWNER_SETUP.md`
- `docs/github_projects/TEST_PLAN.md`
- `docs/github_projects/RUNBOOK.md`
- `docs/github_projects/VERIFICATION_REPORT.md`
- `docs/github_projects/ARTIFACT_MANIFEST.md`
- `docs/github_projects/SHA256SUMS`

## Intended Project

- owner: `arumajirou`
- title: `Loto Forecast Platform Governance`
- visibility: `PRIVATE`
- linked repository: `arumajirou/loto_forecast_platform`
- authority: `governance_only`

The Project preserves distinct workflow and evidence states. `Done` does not mean `VERIFIED`, and a
failed or blocked item must not be visually normalized into success.
