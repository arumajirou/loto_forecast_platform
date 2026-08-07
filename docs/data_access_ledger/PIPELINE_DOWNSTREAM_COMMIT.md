# Pipeline downstream commit transaction

Status: `STACKED_ADOPTION / OPT_IN / IDEMPOTENT SAGA`

This lane consumes a `READY_FOR_DOWNSTREAM_COMMIT` output produced by
`run_trusted_vertical_slice_with_ledger.py`. It does not recompute forecasts.
It revalidates immutable staged evidence and then performs downstream writes
through a journaled, restartable transaction.

## Required preflight evidence

The transaction requires all staged artifacts from PR #144 as regular,
non-symlink files. Before any downstream write it:

1. parses JSON with duplicate-key rejection;
2. reloads and freshly validates `pipeline_data_access_ledger.json`;
3. requires the saved validation report and fresh result to match exactly;
4. requires `pipeline_data_access_report.json` to be a complete `PASS`;
5. verifies the HMAC forecast seal and exact sealed payload;
6. verifies Run ID, ledger SHA-256, forecast identity, and champion metrics;
7. hashes every immutable staged artifact;
8. derives a deterministic SHA-256 `commit_id`.

The original `downstream_commit_plan.json` remains immutable. Completion is
recorded in a separate `downstream_commit_receipt.json`.

## Saga order

The transaction runs these steps in order:

```text
release_bundle
artifact_store
mlflow
legacy_registry
platform_registry
event_publication
```

Registry and event writes do not start until release, artifact-store, and
MLflow steps have succeeded. The MLflow run uses the deterministic
`loto_commit_id` tag and is looked up before creating another run.

Every step is persisted to `downstream_commit_state.json` with status,
attempt count, timestamps, result, and error. Successful steps are skipped on
retry. Before and after every step, all staged artifacts are rehashed.

## Idempotency controls

- release bundle: reuse only after ID, artifact set, hash, and size validation;
- artifact store: content-addressed writes plus stored-object hash verification;
- MLflow: search by deterministic commit tag before creating a run;
- legacy Registry: verify forecast primary-key content and detect the
  deterministic commit stage event;
- PlatformRegistry: exact-row verification, task upsert, candidate-only model
  registration, and deterministic commit audit;
- EventPublisher: scan for an existing event carrying the commit ID;
- final receipt: a valid matching receipt short-circuits all side effects.

A lock file prevents concurrent writers. A leftover lock is not deleted
automatically; the transaction reports a retryable block so an operator can
inspect the process and journal first.

## Downstream status

A complete transaction records:

```text
DOWNSTREAM_COMMITTED
```

The registered model status remains:

```text
CANDIDATE
```

This does not promote a model or certify it for production.

## Artifacts added by the transaction

- `release_bundle.json`
- `artifact_index.json`
- `downstream_commit_state.json`
- `downstream_commit_receipt.json`
- local Registry/PlatformRegistry/event files when their default local paths
  are used
- content-addressed artifact-store files
- an MLflow run tagged by commit ID

## Command

```bash
export LOTO_FORECAST_SEAL_SECRET='replace-with-at-least-16-bytes'

uv run python scripts/commit_trusted_vertical_slice.py \
  --output /absolute/path/to/staged-run \
  --registry-path /absolute/path/registry.sqlite3 \
  --platform-registry-url sqlite:////absolute/path/platform.sqlite3 \
  --artifact-store /absolute/path/artifact-store \
  --events-path /absolute/path/events.jsonl \
  --mlflow-tracking-uri http://127.0.0.1:5050
```

## Explicit non-claims

This transaction performs candidate registration and evidence publication
only. It does not promote a model, open a designated Holdout split, execute a
future Actual Source read, provide trusted-time Prediction Lock certification,
or certify model runtime/GPU execution. A synthetic or focused-test PASS is
not a real campaign certification.
