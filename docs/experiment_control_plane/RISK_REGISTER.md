# Risk Register

| ID | Risk | Likelihood / Impact | Control | Evidence / Owner |
|---|---|---|---|---|
| R-001 | Editable GitHub metadata treated as approval | M / Critical | exact-subject ApprovalRecord; labels/comments intake-only | approval tests / governance owner |
| R-002 | Duplicate run from retries | M / High | transactional idempotency key and unique constraints | concurrency tests / controller owner |
| R-003 | Stale worker publishes after takeover | M / Critical | monotonic fencing on every mutation | lease tests / agent owner |
| R-004 | Secret appears in plan/log/URI | M / Critical | allowlist logging, URI parser, secret scan, separate lane users | security report / security owner |
| R-005 | GitHub outage loses state | L / High | canonical DB and outbox; GitHub as projection | outage test / platform owner |
| R-006 | Evidence URI points to changed bytes | M / Critical | content hash, size, signature/receipt verification | verifier receipt / evidence owner |
| R-007 | Actions artifact expires | H / High | external durable storage; artifact is transport only | retention audit / operations owner |
| R-008 | Long job trapped in Actions/token lifetime | M / High | enqueue-and-exit control job; durable agent | E2E test / architecture owner |
| R-009 | Self-hosted runner executes untrusted PR | M / Critical | manual owner gate, no PR triggers, ephemeral/isolated workspace | runner config / operations owner |
| R-010 | Paid API runaway cost | M / High | max requests/tokens/cost, circuit breaker, separate approval | cost report / API lane owner |
| R-011 | Actual leakage before Prediction Lock | L / Critical | trusted-time and data-access evidence gates | negative test / evaluation owner |
| R-012 | Best seed/first place auto-promoted | M / Critical | multi-seed/baseline gate and separate promotion subject | evaluation/promotion evidence |
| R-013 | Parallel PR duplicates an authority | H / High | fresh ownership audit and stop-on-conflict | audit report / PR author |
| R-014 | Personal repository lacks role separation | H / High | reduced-assurance record; organization migration plan | approval report / repository owner |
| R-015 | GitHub plan lacks Environment approval | M / Medium | feature check; application-level approval fallback | settings evidence / owner |
| R-016 | CI zero-step failure misclassified | H / Medium | Issue #58 taxonomy; no blind reruns | workflow evidence / CI owner |
| R-017 | In-memory tests mistaken for durability proof | M / High | explicit non-claims; real PostgreSQL/object-store certification | verification report / QA |
| R-018 | Project status drifts from canonical state | M / Medium | outbox, source revision, reconciliation | projection report / integration owner |
