# Implementation Plan

## Wave 0 — pre-implementation audit

For every PR:

1. Fetch default branch and latest main SHA.
2. Search open/closed PRs, Issues, and branches by purpose and package path.
3. Inspect PRs #120–#134 and any newer cross-cutting PR.
4. Record exact owned and forbidden paths.
5. Stop on duplicate or semantic overlap.
6. Create an isolated branch from the re-fetched main SHA.
7. Do not modify a dirty local worktree.

## Wave 1 — dependency-light foundations

### PR 1: Durable Run Lifecycle Contract v1

Deliver:

- strict contracts;
- canonical hashing;
- transition matrix;
- event-chain validator;
- idempotency calculation;
- lease/fencing logic;
- in-memory repository;
- focused tests;
- docs and manifests.

Do not deliver SQL, external workflow engine, API endpoints, or pipeline integration.

### PR 2: Clock Health Gate v1

Deliver:

- normalized observation;
- policy and decision;
- injected parser fixtures;
- monotonic step detection;
- Prediction Lock precondition adapter interface only.

Do not modify PR #125 schemas or existing Prediction Lock implementation.

### PR 3: Provider Sandbox Contract v1

Deliver:

- strict sandbox policy;
- environment and mount validators;
- argv builders for one preferred backend and one interface placeholder;
- effective-policy verifier;
- fake executable tests.

Do not migrate providers or claim a real security boundary until target-host execution passes.

## Wave 2 — persistence

### PR 4: Database Migration Foundation v1

Deliver:

- reviewed Alembic dependency change;
- lock update;
- Alembic environment;
- migration CLI;
- non-destructive baseline;
- offline SQL;
- ephemeral upgrade/downgrade tests;
- legacy schema inventory report.

### PR 5: Persistence Outbox and Reconciliation v1

Deliver:

- migration revisions for new operational tables;
- SQLAlchemy models and repositories;
- dispatcher and reconciliation core;
- fake destination protocols;
- PostgreSQL-focused concurrency tests where available;
- no live MLflow production connection.

## Wave 3 — target-host verification

### PR 6: Target-host Integration Fault Harness v1

Deliver:

- Docker/Testcontainers target-host preflight;
- PostgreSQL and Toxiproxy scenarios;
- process-kill and duplicate-command tests;
- deterministic scenario inventory;
- recovery and reconciliation report;
- SHA-256 artifact package.

## Wave 4 — later operational work

Tracked separately:

1. pgBackRest backup/restore certification;
2. object-store versioning and immutability;
3. Syft SBOM and Cosign/SLSA attestation;
4. SOPS + age secret workflow;
5. SLO, burn-rate, Alertmanager, Blackbox probes;
6. point-in-time feature join;
7. Model Confidence Set / SPA;
8. Temporal or Dagster adapter only after state-machine experience.

## Review gates

A PR cannot advance from Draft until:

- scope and duplicate audit passes;
- focused tests pass;
- Ruff, mypy, compileall pass locally;
- relevant smoke passes;
- manifest and SHA256SUMS verify;
- remote Git blobs match tested bytes;
- no protected data was opened;
- CI either runs actionable steps or remains explicitly blocked;
- a human reviews non-claims and rollback.

No merge is performed by these prompts.
