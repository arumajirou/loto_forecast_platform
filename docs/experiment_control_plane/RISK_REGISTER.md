# Risk Register

| ID | Risk | Impact | Mitigation |
|---|---|---|---|
| R-001 | overlap with PR #139 generic GitHub work | High | domain-only scope and fresh audit |
| R-002 | overlap with PR #137 Promotion | Critical | experiment scopes exclude promotion/deployment |
| R-003 | label/comment starts execution | Critical | reviewed plan + scoped approval + explicit dispatch |
| R-004 | long Actions job times out or loses token | High | Local Agent owns long run |
| R-005 | compromised self-hosted runner | Critical | ephemeral short jobs, no unknown code, least secrets |
| R-006 | PAT leakage | Critical | GitHub App short-lived token |
| R-007 | Project presented as authority | High | projection-only contract |
| R-008 | Actions artifact expires | High | external evidence store and hash index |
| R-009 | personal repo cannot enforce role separation | High | explicit limitation; organization migration path |
| R-010 | paid API cost overrun | High | reservation, hard caps, circuit breaker |
| R-011 | duplicate dispatch | High | semantic idempotency key |
| R-012 | stale agent writes state | High | lease/fencing through PR #140 |
| R-013 | GitHub outage loses completion update | Medium | durable outbox/reconciliation |
| R-014 | secret appears in Check/Project/URI | Critical | allowlist/redaction/secret scan |
| R-015 | mutable plan after approval | Critical | Git blob SHA and plan hash |
| R-016 | trial explosion floods GitHub | Medium | trials remain MLflow/DB |
| R-017 | Issue #58 makes workflows untestable | High | contracts first; workflow PR blocked |
| R-018 | evidence index points to missing object | High | remote verification status and completion block |
| R-019 | Release confused with promotion | High | explicit non-authority and PR #137 boundary |
| R-020 | foundation not adopted | High | one bounded real workflow migration after each foundation |
