# Handoff

## Recommended first task

Use:

```text
prompts/01_DURABLE_RUN_LIFECYCLE.md
```

Reason:

- lowest overlap with PRs #120–#134;
- no root dependency change;
- no database or service requirement;
- provides contracts needed by later persistence work;
- can be verified with deterministic focused tests.

## Work not yet authorized

- merge or Ready transition;
- main modification;
- Holdout or Prospective access;
- production database migration;
- production backup/restore;
- provider migration to sandbox;
- Temporal/Dagster deployment.

## Dependencies to monitor

- PR #120 may affect version and `pyproject.toml`;
- PR #121 may provide configuration types later;
- PR #123 provides runtime executor interfaces for later sandbox integration;
- PR #124/#129 provide access evidence for later lifecycle integration;
- PR #125 provides trusted evidence semantics for later clock/Actual integration;
- PR #127 provides readiness endpoints for later dependency probes;
- PR #131 owns telemetry and OSS UI design;
- PR #133 owns GitHub audit;
- PR #134 owns source intake.

## Review questions

1. Are phase and status separate?
2. Can a stale worker commit?
3. Does duplicate delivery create duplicate effects?
4. Can application startup migrate the DB?
5. Is local clock health being confused with trusted time?
6. Are requested sandbox controls independently observed?
7. Does a synthetic/fake PASS remain clearly non-formal?
8. Can a fault harness touch a production service?
9. Are all non-claims explicit?
10. Is rollback possible without deleting evidence?
