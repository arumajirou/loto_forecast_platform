# Handoff

## Repository owner actions

1. Review the fact-check corrections and ownership boundaries.
2. Keep the documentation PR Draft until content review is complete.
3. Resolve or explicitly track Issue #58; do not treat its zero-step runs as code failure.
4. Decide whether granular approval requires migration to a GitHub organization.
5. Decide the durable evidence stack and secret manager before PR-4/5.
6. Authorize only PR-1 first; do not start all implementation stages concurrently.

## Implementer actions

- copy `IMPLEMENTATION_PROMPT.md` and set `TARGET_STAGE=plan-contract`;
- start from latest main, not this documentation branch;
- fetch this documentation PR as read-only design evidence if it remains unmerged;
- recheck all neighboring PRs and stop on semantic/path overlap;
- preserve current repository conventions, strict configuration and evaluation protocol;
- create a Draft PR and report exact tests/non-claims.

## Decisions still required

```text
controller initial deployment: local service or server
canonical database: PostgreSQL target and development fallback
object storage: local content-addressed / S3-compatible / other
approval role model under personal repository
GitHub App ownership and key storage
retention classes and backup destination
network policy for model downloads and paid APIs
```

## Definition of a safe handoff

A handoff is complete when another engineer can identify the current main SHA, owned paths, upstream dependencies, exact contracts, local test commands, rollback, blocked checks and prohibited side effects without relying on chat history.
