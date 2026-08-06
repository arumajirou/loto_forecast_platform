# Risk Register

| ID | Risk | Probability | Impact | Mitigation | Stop condition |
|---|---|---:|---:|---|---|
| R-001 | Duplicate work with open Draft PR | High | High | fresh PR/branch/path audit | same-purpose implementation found |
| R-002 | State machine too generic to fit workflows | Medium | High | phase/status separation, workflow profiles | unreviewed special cases |
| R-003 | Stale worker commits after takeover | Medium | Critical | DB lease + fencing token | adapter cannot enforce token |
| R-004 | Outbox claims exactly-once delivery | High | High | state “exactly-once effect”, receipts/read-back | destination cannot deduplicate/verify |
| R-005 | SQLite tests hide PostgreSQL behavior | High | High | target-host Postgres tests | no Postgres evidence |
| R-006 | Alembic baseline misrepresents legacy DB | Medium | Critical | no auto-stamp; inventory first | unknown schema treated current |
| R-007 | Clock health confused with trusted time | Medium | High | explicit semantic separation | status mapping raises trust |
| R-008 | Sandbox policy not effective on host | Medium | Critical | effective evidence and fault tests | only requested policy recorded |
| R-009 | Secrets leak into argv/logs/artifacts | Medium | Critical | allowlist, redaction, scans | secret pattern finding |
| R-010 | Fault harness damages real services | Low | Critical | isolated containers and namespaces | production DSN detected |
| R-011 | Retry storm | Medium | High | bounded attempts/backoff/poison state | unbounded retry path |
| R-012 | Reconciliation overwrites hash conflict | Low | Critical | manual review state | automatic overwrite |
| R-013 | Root dependency conflict with open PRs | High | Medium | wait/rebase-free plan, one lock update | pyproject/uv.lock concurrent owner |
| R-014 | CI pre-run blocker misclassified as test failure | High | Medium | inspect steps/logs; issue #58 policy | no actionable step/log |
| R-015 | Foundation proliferation without adoption | High | High | each foundation has bounded adoption PR | no target workflow selected |
| R-016 | Holdout/Prospective accidental access | Low | Critical | forbidden paths, negative tests | access evidence appears |
| R-017 | Full pytest run too early wastes resources | Medium | Medium | focused gates first | implementation unstable |
| R-018 | External workflow engine added prematurely | Medium | Medium | collect state-machine evidence first | Temporal/Dagster added in v1 |
