# Operational Resilience Expansion Blueprint v1

## Status

```text
DOCUMENTATION_ONLY
FACT_CHECKED_AT=2026-08-06T16:36:00+09:00
REPOSITORY=arumajirou/loto_forecast_platform
DEFAULT_BRANCH=main
OBSERVED_MAIN_HEAD=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
IMPLEMENTATION_NOT_STARTED
HOLDOUT_NOT_OPENED
PROSPECTIVE_NOT_OPENED
MERGE_NOT_AUTHORIZED
```

## Purpose

This package defines the next implementation program for operational resilience that remained
insufficiently covered after the forecasting, evaluation, runtime-certification, leakage-prevention,
prediction-lock, actual-source, observability, feature-availability, and repository-audit plans.

The target is not a new forecasting model. The target is a platform that can:

1. resume safely after interruption;
2. prevent duplicate or stale workers from committing results;
3. reconcile partial persistence across PostgreSQL, MLflow, Parquet, and artifact storage;
4. upgrade database schemas deliberately;
5. block prediction locking when the host clock is unhealthy;
6. execute untrusted provider code inside a constrained sandbox;
7. prove behavior under real dependency failure and recovery.

## Current GitHub ownership boundary

The following open Draft PRs already own adjacent responsibilities and must not be copied:

| PR | Existing responsibility | Boundary preserved by this package |
|---:|---|---|
| #120 | version single source and BUILD_INFO | consume after merge; do not redefine version |
| #121 | strict configuration foundation | do not add competing configuration schemas |
| #123 | provider-neutral runtime certification | sandbox wraps execution; it does not replace runtime evidence |
| #124 / #129 | Data Access Ledger and research adapter | lifecycle references ledger evidence; it does not duplicate access events |
| #125 | trusted-time and Actual-source evidence schemas | clock health is an operational precondition, not trusted timestamp proof |
| #127 | API liveness/readiness and dependency probes | do not add duplicate `/livez` or `/readyz` endpoints |
| #128 / #134 | research expansion and Research Source Registry | no model intake or source registry changes |
| #131 | evaluation, telemetry, OSS UI blueprint | do not duplicate metrics, traces, dashboards, or evaluation protocol |
| #132 | Feature Availability Registry | no competing feature manifest |
| #133 | read-only GitHub audit exporter | no competing GitHub audit or PR graph exporter |

## Recommended implementation order

```text
Wave 0  Re-audit and ownership lock
Wave 1  Durable Run Lifecycle Contract v1
Wave 1  Clock Health Gate v1
Wave 1  Untrusted Provider Sandbox Contract v1
Wave 2  Database Migration Foundation v1
Wave 2  Persistence Outbox and Reconciliation v1
Wave 3  Target-host Integration Fault Harness v1
Wave 4  Backup/Restore, SBOM/Attestation, SLO, secrets, point-in-time join
```

The first three PRs are deliberately add-only and dependency-light. Database and fault-injection
work follows only after the contracts and ownership boundaries stabilize.

## Definition of success

A PR is not successful merely because schemas import or synthetic tests pass. The evidence ladder is:

```text
STATIC_CONTRACT_VERIFIED
→ FOCUSED_TESTS_PASS
→ REAL_STORAGE_ADAPTER_VERIFIED
→ TARGET_HOST_EXECUTED
→ FAILURE_INJECTED
→ RECOVERY_VERIFIED
→ RECONCILIATION_COMPLETE
→ FORMAL_OPERATIONAL_CERTIFICATION
```

Every stage must preserve explicit non-claims.

## Package contents

- Requirements, functional specification, architecture, basic and detailed design
- Data contracts and state-transition rules
- Implementation and migration plans
- Execution schedule and PR dependency graph
- Test plan, verification boundary, risk register, traceability matrix
- Operator runbook and handoff
- Ready-to-paste master and per-PR implementation prompts
- Machine-readable backlog, artifact manifest, SHA-256 inventory

## Immediate recommendation

Start with `feat/durable-run-lifecycle-contract-v1`. It has the lowest overlap risk and does not
require root dependency, database, model, GPU, Holdout, Prospective, API, Registry, or Promotion
changes.
