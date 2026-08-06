# Test Plan

## Order

```text
contract/unit
→ property/negative
→ focused package
→ compileall
→ Ruff
→ mypy
→ fake GitHub/API integration
→ target-host integration
→ fault injection
→ full pytest
→ actionable GitHub Actions
```

## Plan contract

- strict unknown/type/range rejection;
- canonical hash stability;
- every result-affecting field changes hash;
- primary Hit@±1 fixed;
- complete secondary metrics and baseline inventory;
- all-seed mean/variance/worst policy;
- chronology and protected-stage rules;
- unpinned code/model rejection;
- budget validation;
- secret-field rejection.

## Approval and dispatch

- wrong plan hash;
- wrong scope;
- expired and consumed approval;
- self-approval limitation evidence;
- duplicate dispatch;
- conflicting duplicate;
- protected-stage absence;
- paid API without budget approval.

## GitHub integration

- Check state mapping;
- bounded Check names;
- idempotent update;
- fake one-hour token refresh;
- least-privilege permission failure;
- Project missing field/permission;
- mutable label never authorizes execution.

## Local Agent

- clean workspace;
- exact plan/code/data verification;
- CPU/GPU/API lane isolation;
- heartbeat;
- cancellation;
- restart/resume;
- stale fencing token;
- evidence upload failure;
- GitHub outage and reconciliation;
- API secret isolation;
- cost cap and circuit breaker.

## Evidence Index

- safe URI;
- size/hash mismatch;
- missing remote;
- revoked object;
- credential/query-token URI;
- complete required inventory;
- Prediction Lock before Actual;
- Actual evidence only post-reveal;
- temporary Actions artifact not accepted as sole long-term evidence.

## Safety regression

No implementation may alter evaluation formulas, baseline semantics, chronological splits, Runtime
Certification, Data Access Ledger, Trusted Evidence, Promotion Governance, Holdout, or Prospective
data without a separately approved integration PR.
