# Traceability Matrix

| Requirement | Design component | Primary test | Planned PR |
|---|---|---|---|
| FR-DL-002 | transition matrix | invalid transition exhaustive test | lifecycle |
| FR-DL-004 | idempotency service | duplicate command test | lifecycle |
| FR-DL-005/006 | lease/fencing | stale worker test | lifecycle/outbox |
| FR-DL-008 | resume | sealed-output resume test | lifecycle adoption |
| FR-CH-002/003 | clock policy | threshold matrix | clock |
| FR-CH-004 | precondition interface | unhealthy lock rejection | clock |
| FR-CH-005 | semantic boundary | no trust promotion test | clock |
| FR-SB-001 | command builder | no-shell assertion | sandbox |
| FR-SB-002 | policy | required-control matrix | sandbox |
| FR-SB-004 | environment filter | secret rejection | sandbox |
| FR-MG-001 | Alembic foundation | dependency/lock check | migrations |
| FR-MG-003 | startup boundary | import-no-migration test | migrations |
| FR-MG-005 | offline SQL | deterministic SQL hash | migrations |
| FR-OR-001 | transaction repository | rollback/commit test | outbox |
| FR-OR-003 | unique key | duplicate insert test | outbox |
| FR-OR-005 | reconciliation | missing/orphan/conflict tests | outbox |
| FR-FH-002 | fault injector | scenario suite | fault harness |
| FR-FH-003 | recovery | eventual consistency test | fault harness |
| NFR-001 | strict models | unknown/coercion tests | all |
| NFR-003 | manifests | tamper test | all |
| NFR-004 | redaction | secret scan | all |
| NFR-008 | Git/data safety | changed-path and non-access audit | all |
