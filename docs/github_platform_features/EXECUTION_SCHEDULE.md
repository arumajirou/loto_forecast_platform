# Execution Schedule — GitHub Platform Features Foundation v1

## 1. Scheduling model

This schedule is dependency-driven rather than date-promised. Calendar dates are assigned only after Issue #58 and repository visibility/plan decisions are resolved.

## 2. Work breakdown

| Stage | Work item | Depends on | Primary evidence | Exit state |
|---|---|---|---|---|
| S0 | Re-audit `main`, duplicate branches/PRs/Issues, settings | none | base SHA and audit record | VERIFIED |
| S1 | Resolve GitHub Actions pre-run blocker #58 | owner settings/billing | run with real steps/logs | VERIFIED |
| S2 | Dependabot foundation | S0 | accepted config and first parsed update cycle | VERIFIED or PARTIALLY_VERIFIED |
| S3 | Projects governance | S0 | field/view/workflow exports | VERIFIED |
| S4 | Pages visibility decision | owner/plan decision | recorded decision | APPROVED or BLOCKED |
| S5 | Public docs audit/build | S1, S4 | strict build artifact and manifest | VERIFIED |
| S6 | Pages deployment | S5 | deployment URL, commit, smoke evidence | VERIFIED |
| S7 | Webhook receiver foundation | S0 | local contract/security tests | VERIFIED_LOCAL |
| S8 | Webhook deployment and adapters | S1, S7 | signed real delivery and observability | VERIFIED_RUNTIME |
| S9 | OSS security fallback | S1 or approved local lane | scanner reports and manifests | VERIFIED |
| S10 | CodeQL eligibility decision | owner/organization/plan | documented entitlement | APPROVED or BLOCKED |
| S11 | CodeQL enablement | S1, S10 | completed analysis and alerts | VERIFIED |
| S12 | Integration verification and handoff | selected stages | final report, screenshots, hashes | VERIFIED |

## 3. Per-PR engineering loop

```text
Observe -> Diagnose -> Plan -> Change -> Focused Test -> Measure
        -> Review -> Final Full Test -> CI once -> Accept or Rollback
```

### Development gate

- current `main` and merge-base recorded;
- working branch unique and clean;
- owned paths defined;
- secrets and large-file boundary defined;
- focused tests identified.

### Local verification gate

- format/lint for changed paths;
- type checks for owned typed surfaces;
- focused pytest;
- compileall;
- feature smoke test;
- negative/security tests;
- artifact/manifest verification.

### Final quality gate

- one full pytest after implementation stabilizes;
- dependency and secret scan;
- repository diff review;
- actionable GitHub Actions run after Issue #58 resolution;
- PR remains Draft until all claims match evidence.

## 4. Parallelism

Safe parallel work:

- Dependabot design and Project configuration may proceed independently.
- Webhook local contract implementation may proceed while Pages visibility is undecided.
- Documentation content preparation may proceed before Actions recovery, but deployment workflow verification cannot.

Serialized work:

- Changes to the same workflow file or root lock;
- webhook schema migration and deployment;
- Pages setting activation and deployment;
- CodeQL and branch-protection changes;
- any repository/account setting change.

## 5. Stop conditions

Stop the current increment when:

- `main` moves and invalidates assumptions;
- duplicate implementation is found;
- Issue #58 remains unchanged and a rerun would repeat zero-step failure;
- Pages visibility cannot be proven safe;
- a secret, private URL, Holdout/Prospective evidence, or unapproved artifact is detected;
- required permissions or plan eligibility are unavailable;
- implementation requires root dependency changes outside approved scope;
- tests expose a promotion, registry, or data-leakage side effect.

## 6. Rollback checkpoints

Every stage records:

- pre-change settings/export;
- branch and commit SHA;
- changed paths;
- feature flag or enablement state;
- rollback command/procedure;
- post-rollback verification;
- retained audit artifacts.

## 7. Definition of done

A stage is done only when its code/configuration, runtime behavior, security controls, observability, documentation, and rollback have all been verified. A file existing in the repository or a UI tab appearing is not sufficient.