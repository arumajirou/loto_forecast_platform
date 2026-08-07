# NeuralForecast Prospective Experiment Registry

## Purpose

This workflow registers one verified NeuralForecast Prospective scoring artifact in
both PostgreSQL and MLflow without mutating the scoring artifact or the original
Prospective prediction run.

The registry is an evidence and observability layer. It does not retrain, re-predict,
select a replacement seed, promote a model, or change the scoring result.

Formal registration requires both backends:

- PostgreSQL for normalized, queryable run, candidate, seed, position, and artifact
  records;
- MLflow for a parent experiment run, per-seed child runs, metrics, parameters, and
  immutable source evidence.

## Commands

Set backend connection information through environment variables. The PostgreSQL
DSN is deliberately not accepted as a command-line argument.

```bash
export LOTO_POSTGRES_DSN='postgresql+psycopg://USER:PASSWORD@HOST:5432/loto'
export MLFLOW_TRACKING_URI='http://mlflow-host:5000'
```

Register a verified scoring artifact:

```bash
uv run --extra postgres --extra mlflow loto-auto-campaign \
  register-scoring \
  --run artifacts/prospective-scoring/<scoring-run> \
  --output artifacts/prospective-registry/<registry-receipt> \
  --registry-namespace production \
  --mlflow-experiment loto-neuralforecast-prospective \
  --artifact-mode metadata
```

Verify a registry receipt without connecting to PostgreSQL or MLflow:

```bash
uv run loto-auto-campaign \
  verify-scoring-registry \
  --run artifacts/prospective-registry/<registry-receipt>
```

Both commands are configless. They do not load the current campaign YAML.

## Required source state

The input must be a PR #64 Prospective scoring artifact for which
`verify-scoring` returns `PASS`. Registration additionally requires readable,
non-empty:

- `ARTIFACT_MANIFEST.json`;
- `SCORING_REPORT.json`;
- `ACTUALS_LOCK.json`;
- complete `SHA256SUMS`;
- `RANKING` CSV and Parquet;
- `SEED_SUMMARY` CSV and Parquet;
- `PER_SEED_METRICS` CSV and Parquet;
- `POSITION_METRICS` CSV and Parquet;
- `BASELINE_COMPARISON` CSV and Parquet;
- copied source manifest, campaign configuration, data contract, prediction lock,
  and verification seal.

Registration is rejected before backend writes when source verification fails.

## Metric contract

The registry preserves the scoring policy rather than recomputing a different
leaderboard.

Primary metric:

```text
Hit@±1
```

Also retained:

- all-position Hit@±1;
- MAE;
- MSE;
- RMSE;
- position-level metrics;
- per-seed metrics;
- seed mean, variance, minimum, maximum, and worst-seed Hit@±1.

The durable payload fixes:

```text
best_seed_only_selection=false
automatic_promotion=false
automatic_retraining=false
```

The scoring artifact's ranking remains informational. Registration cannot turn its
first-ranked model into a production champion.

## Stable identity and idempotency

`registry_id` is deterministic for:

- registry schema version;
- registry namespace;
- scoring ID;
- scoring report SHA-256;
- scoring artifact manifest SHA-256;
- scoring `SHA256SUMS` SHA-256;
- redacted MLflow tracking URI;
- MLflow experiment name;
- artifact mode.

`payload_sha256` covers the full normalized registry payload. The PostgreSQL table
also enforces uniqueness for `(scoring_id, registry_namespace)`.

A repeated operation with the same identity and payload may recover existing MLflow
runs and refresh the prepared PostgreSQL rows. A different payload for an existing
identity fails closed. To intentionally create an independent registration, use a
new explicit registry namespace.

## Dual-backend transaction sequence

The operation uses a fail-closed staged contract:

```text
verify scoring artifact
        ↓
normalize candidate/seed/position/artifact records
        ↓
PostgreSQL PREPARE: PENDING_MLFLOW
        ↓
MLflow parent run + per-seed child runs
        ↓
PostgreSQL FINALIZE: PASS
        ↓
write and verify independent local receipt
```

If MLflow or PostgreSQL finalization fails after preparation, the implementation
best-effort marks the prepared PostgreSQL run `BLOCKED`. It does not report a
partial write as formal success.

No distributed transaction is claimed. The deterministic identity and backend
receipts make retries auditable and idempotent.

## PostgreSQL schema

The implementation creates five namespaced tables:

```text
nf_prospective_registry_runs
nf_prospective_registry_candidates
nf_prospective_registry_seed_metrics
nf_prospective_registry_position_metrics
nf_prospective_registry_artifacts
```

### Run record

The run table retains:

- registry ID and namespace;
- scoring ID and operational status;
- source run ID;
- prediction-lock SHA-256;
- scoring report SHA-256;
- scoring artifact manifest SHA-256;
- scoring `SHA256SUMS` SHA-256;
- normalized payload SHA-256;
- redacted MLflow URI, experiment, and parent run ID;
- complete JSONB payload, backend receipt, and failure evidence.

### Candidate record

One row per model or baseline aggregate records:

- source type, model/baseline name, and track;
- seed count;
- Hit@±1 mean, variance, minimum, maximum, and worst seed;
- all-position Hit@±1 mean;
- MAE, MSE, and RMSE means;
- audit ranking.

### Seed and position records

Per-seed rows preserve each seed before aggregation. Position rows use a canonical
row hash that includes candidate identity, backend, configuration index, position,
seed, unique ID, and prediction variant so multiple configurations do not collide.

### Artifact records

Every scoring artifact inventory row retains path, size, and SHA-256. The core
manifest, report, actual lock, and SHA list are added explicitly.

## MLflow hierarchy

Each registration uses one parent run tagged with:

- `registry_id`;
- `scoring_id`;
- `registry_role=parent`;
- `payload_sha256`.

Each per-seed model or baseline row uses a child run tagged with:

- `mlflow.parentRunId`;
- `registry_role=seed`;
- candidate key;
- seed token;
- payload SHA-256.

The parent records candidate/seed/position counts and numeric champion metrics from
the immutable scoring report. Child runs record Hit@±1, all-position Hit@±1, MAE,
MSE, and RMSE for that exact seed row.

`artifact-mode=metadata` logs the registry payload and copied core source evidence.
`artifact-mode=full` additionally logs the complete verified scoring artifact.
Neither mode changes the original files.

## Secret handling

- PostgreSQL DSN is read only from the configured environment-variable name.
- Durable payloads store the environment-variable name, never the DSN.
- MLflow and PostgreSQL receipt URIs redact passwords and query values.
- Failure sanitation removes the complete URI, URI password, and recognized token,
  password, secret, credential, and API-key query values.
- The local report explicitly records `secrets_persisted=false`.

This is application-level redaction, not a secrets manager. Production credentials
should still be supplied through an operating-system or orchestration secret store.

## Local receipt

The independent receipt directory contains:

```text
REGISTRY_PAYLOAD.json
BACKEND_RECEIPTS.json
REGISTRY_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
source_evidence/
```

`BACKEND_RECEIPTS.json` records attempted phases and backend receipts. A blocked
operation may contain no completed backend receipt, but its structured envelope is
still non-empty and verifiable.

The receipt is built in a temporary directory and atomically renamed only after its
integrity verifier passes. Existing output is not overwritten. Output inside the
source scoring artifact is rejected before its parent directory is created.

## Receipt verification

`verify-scoring-registry` operates read-only and does not contact external systems.
It verifies:

- no symbolic links;
- complete `SHA256SUMS`;
- canonical payload and manifest hashes;
- exact file inventory;
- registry and payload identity agreement;
- report/backend-receipt equality;
- attempted-phase consistency;
- copied source evidence hashes and sizes;
- Hit@±1 priority and no-best-seed-only policy;
- PASS receipts for PostgreSQL prepare, MLflow, and PostgreSQL finalize;
- MLflow parent-run equality with PostgreSQL finalization;
- the current source scoring artifact when it remains available.

If the source scoring directory has been archived or removed, copied evidence remains
verifiable and `source_reverification=NOT_AVAILABLE` is reported.

Receipt integrity does not prove that an external PostgreSQL or MLflow service still
contains the records. Live backend reconciliation is a separate operational check.

## Operational states

```text
PASS
  source verified
  PostgreSQL prepared
  MLflow recorded
  PostgreSQL finalized
  receipt integrity PASS

BLOCKED
  source and receipt integrity may be valid
  one or more required backend phases did not complete
  CLI exits 2

FAIL
  command input or local integrity contract failed
  CLI exits 2
```

A `BLOCKED` receipt is evidence of an unsuccessful registration attempt, not a
successful experiment registration.

## Validation boundary

Dependency-minimal tests cover:

- successful dual-backend order and source immutability;
- relocated receipt verification after source removal;
- deterministic registry identity and payload hash;
- MLflow failure followed by PostgreSQL blocked transition;
- missing PostgreSQL DSN before backend calls;
- secret redaction for complete URIs, passwords, and tokens;
- receipt mutation detection;
- position-key uniqueness across configurations;
- output-inside-source rejection without filesystem mutation;
- both-backends-required configuration;
- URI redaction and namespaced PostgreSQL tables;
- MLflow parent/per-seed child creation and retry reuse;
- configless CLI routing and structured failures.

The local tests use injected backend doubles and a pandas pickle stand-in where a
Parquet engine is unavailable. They do not prove live PostgreSQL connectivity,
transaction behavior on a real server, live MLflow behavior, formal Parquet I/O,
repository-wide lint/type/test success, or production registration.

## Required target-host verification

Before promotion or operational use:

1. install the `postgres` and `mlflow` extras with the locked project environment;
2. run repository Ruff, compileall, mypy, focused pytest, and full pytest last;
3. provision a disposable PostgreSQL schema and MLflow experiment;
4. register one verified synthetic scoring artifact;
5. query all five PostgreSQL tables and compare counts and hashes;
6. inspect the MLflow parent and all per-seed children;
7. repeat the same registration and require reuse without duplicate rows/runs;
8. force an MLflow failure and confirm PostgreSQL becomes `BLOCKED`;
9. verify the receipt after removing the source scoring directory;
10. retain logs and backend IDs in the verification report.

## Not claimed

This implementation does not claim:

- live PostgreSQL or MLflow execution in the authoring environment;
- a distributed transaction across PostgreSQL and MLflow;
- cryptographic signing or external trusted timestamping;
- remote backend durability after receipt creation;
- real Prospective accuracy improvement or baseline superiority;
- model registration, champion promotion, deployment, or retraining;
- GPU execution;
- merge readiness.
