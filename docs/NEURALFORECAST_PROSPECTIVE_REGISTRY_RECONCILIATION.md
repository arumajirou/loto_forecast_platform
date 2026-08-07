# NeuralForecast Prospective Registry Reconciliation

## Purpose

This stage verifies that one immutable local Prospective registry receipt still agrees with the records stored in PostgreSQL and MLflow. It is read-only: it does not repair a database row, rewrite an MLflow run, promote or deploy a model, or start retraining.

Formal reconciliation requires agreement across three evidence domains:

1. the locally verified registry receipt from Draft PR #72;
2. the PostgreSQL registry tables;
3. the MLflow parent run, every per-seed child run, and selected immutable artifacts.

## Stack position

```text
Prospective prediction lock
-> Actual ingestion and scoring
-> PostgreSQL + MLflow registration
-> Registry reconciliation
-> Operational monitoring and alert policy
```

This change is stacked on `agent/p0-prospective-experiment-registry` at SHA `47a9da201144988499417d2db9a408069d903ca7`.

## Commands

Formal three-way reconciliation:

```bash
export LOTO_POSTGRES_DSN='postgresql+psycopg://USER:PASSWORD@HOST:5432/loto'
export MLFLOW_TRACKING_URI='http://mlflow-host:5000'

uv run --extra postgres --extra mlflow loto-auto-campaign \
  reconcile-scoring-registry \
  --run artifacts/prospective-registry/<registry-receipt> \
  --output artifacts/prospective-registry-reconciliation/<run>
```

Independent offline verification of the captured reconciliation artifact:

```bash
uv run loto-auto-campaign \
  verify-registry-reconciliation \
  --run artifacts/prospective-registry-reconciliation/<run>
```

`--skip-remote-artifact-check` is diagnostic only. Formal reconciliation downloads and hashes the selected MLflow artifacts.

## Source receipt gate

Backend reads do not begin until `verify-scoring-registry` returns `PASS`. Only a registry receipt whose operational status is also `PASS` can receive formal three-way reconciliation.

The expected state is reconstructed from immutable copied evidence, not from backend row counts alone. It includes:

- registry ID, scoring ID, namespace, payload SHA-256, and source hashes;
- every candidate aggregate, including Hit@±1 mean, variance, minimum, maximum, all-position Hit@±1, MAE, MSE, RMSE, rank, and worst-seed Hit@±1;
- every candidate and seed pair;
- every position metric row and variant;
- the exact artifact path, size, and SHA-256 inventory;
- the expected MLflow parent run ID and per-seed child set.

Best-seed-only selection is not permitted.

## PostgreSQL checks

The PostgreSQL probe uses read-only `SELECT` statements. It checks:

- exactly one registry run row;
- `status=PASS`;
- registry/scoring identity, namespace, payload and source hashes;
- MLflow experiment and parent run identity;
- exact candidate keys and aggregate metrics;
- exact seed keys and per-seed metrics;
- exact position row keys and position metrics;
- exact artifact paths, sizes, and hashes;
- duplicate, missing, and unexpected keys.

## MLflow checks

The MLflow probe checks:

- exactly one parent run for the registry ID;
- parent status `FINISHED`;
- registry, scoring, namespace, payload, and priority-metric tags/params;
- parent ID equality with the local receipt and PostgreSQL;
- the exact `(candidate_key, seed_token)` child set;
- no duplicate children;
- each child is `FINISHED`, points to the expected parent, and has the expected payload hash;
- Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE for every seed;
- selected immutable artifact hashes.

For metadata mode, the selected remote artifacts include the registry payload and copied scoring artifact manifest. Full mode additionally checks the scoring report stored under the full scoring artifact.

## Status classification

### PASS

Both backend reads completed and every expected value matched.

### DRIFT

Both backends were reachable, but one or more records, metrics, identities, parent-child relationships, or artifact hashes disagreed.

### BLOCKED

Formal comparison could not run because required backend configuration was missing or a backend query/download failed.

No status triggers automatic repair.

## Output artifact

Each attempt creates an atomic directory containing:

```text
RECONCILIATION_EXPECTED.json
POSTGRES_SNAPSHOT.json
MLFLOW_SNAPSHOT.json
RECONCILIATION_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
source_receipt/
```

`source_receipt/` is an exact copy of the original registry receipt. The offline verifier checks complete SHA coverage, canonical hashes, exact inventory, status-specific evidence rules, the copied receipt tree hash, and copied receipt verification. It contacts neither PostgreSQL nor MLflow.

An offline verification `PASS` proves the captured audit artifact is internally consistent; it does not prove the remote services have remained unchanged since capture.

## Safety and secrets

- PostgreSQL and MLflow are accessed read-only.
- The PostgreSQL DSN is read from an environment variable and is not persisted.
- Durable URIs are redacted.
- Backend exceptions use the existing registry secret-redaction helper.
- `automatic_repair=false`, `automatic_promotion=false`, and `automatic_retraining=false` are persisted.
- This application-level redaction is not a substitute for a secrets manager.

## Metric boundary

Hit@±1 remains the priority metric. The audit also retains all-position and position-level Hit@±1, MAE, MSE, RMSE, every seed, and seed mean/variance/minimum/maximum/worst values.

A reconciliation `PASS` means storage consistency only. It does not mean accuracy improved, a model beat every baseline, or promotion/deployment is allowed.

## Validation boundary

Dependency-minimal evidence completed for this change:

```text
focused tests = 13 passed
synthetic reconciliation smoke = 14 assertions passed
Python AST parse = PASS
Python lines over 100 characters = 0
```

The focused tests use injected backend doubles. Live PostgreSQL reads, live MLflow reads and artifact downloads, formal pyarrow execution, repository Ruff/mypy/pytest, GitHub Actions, and production reconciliation remain separate target-host requirements.
