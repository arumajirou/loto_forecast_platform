# NeuralForecast prospective prediction lock

## Purpose

Prospective predictions must be fixed before the corresponding actual values are
known. A per-task `prediction_freeze.json` already records the prediction file
hash during task execution. This layer adds one campaign-level
`PREDICTION_LOCK.json` after every prospective task succeeds and after the run's
promotion and lineage evidence is written.

A prospective run is not successful unless this campaign lock is created and
later passes standard verification.

## Automatic execution order

The normal prospective command remains:

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign.yaml \
  run \
  --stage prospective \
  --source-run artifacts/validate-trials/<verified-run> \
  --predecessor-run artifacts/holdout/<verified-run> \
  --coverage-run artifacts/api-coverage/<verified-run> \
  --runtime-run artifacts/neuralforecast-db/<runtime-run> \
  --output artifacts/prospective/<run>
```

The implementation performs:

```text
promotion gate
→ prospective task execution
→ task-level prediction_freeze.json
→ run manifest PASS
→ LINEAGE.json
→ PREDICTION_LOCK.json
→ root SHA256SUMS
```

There is intentionally no command for retroactively adding a lock to an already
sealed run. If `VERIFICATION_SEAL.json` exists while the campaign lock is absent,
lock creation fails.

## Lock prerequisites

The campaign lock requires:

- run manifest `status=PASS`;
- run stage `prospective`;
- promotion gate `PASS`;
- lineage `PASS`;
- non-empty code, data, and lineage-chain hashes;
- positive and equal planned/completed task counts;
- one task-level `prediction_freeze.json` for every completed task;
- every task manifest `PASS`;
- task stage `prospective`;
- `actual_known=false` in every task freeze;
- load and prediction success;
- output shape match;
- finite prediction values;
- pre-save and post-load prediction match;
- `cpu_fallback=false`;
- valid task and model-bundle `SHA256SUMS`;
- no symbolic links;
- no actual, observed, realized, or outcome artifact filenames.

## Locked evidence

`PREDICTION_LOCK.json` binds the following run evidence:

- run ID and stage;
- code SHA-256;
- data SHA-256;
- lineage chain SHA-256;
- planned and completed task counts;
- `campaign_config.json`;
- `data_contract.json`;
- `PROMOTION_GATE.json`;
- `LINEAGE.json`.

For each prospective task it records:

- task path and task contract;
- task freeze timestamp;
- task manifest;
- task `SHA256SUMS`;
- task `prediction_freeze.json`;
- pre-save prediction Parquet;
- post-load prediction Parquet;
- load/predict verification;
- model-bundle manifest;
- model-bundle `SHA256SUMS`.

Every file record contains a relative path, SHA-256, and byte size. A canonical
`lock_sha256` covers the complete lock payload, including the lock timestamp.

## Manifest fields

A successful lock adds:

```text
prediction_lock_schema_version=all-auto-prediction-lock-v1
prediction_lock_status=LOCKED
prediction_lock_path=PREDICTION_LOCK.json
prediction_lock_sha256=<file-sha256>
prediction_task_count=<completed-task-count>
prediction_locked_at=<UTC timestamp>
actual_known_at_lock=false
```

The root `SHA256SUMS` is regenerated after the lock and manifest are written.

## Failure contract

If campaign locking fails, the run is downgraded rather than being reported as a
successful prospective result.

```text
status=PARTIAL
prediction_lock_status=FAILED
prediction_lock_path=PREDICTION_LOCK_FAILURE.json
actual_known_at_lock=UNKNOWN
```

`PREDICTION_LOCK_FAILURE.json` records the failure time, error type, and error
message. The successful lock file is not left behind.

## Standard verification

Run:

```bash
uv run loto-auto-campaign verify --run artifacts/prospective/<run>
```

Before creating or accepting a verification seal, standard verification checks:

- lock schema and `LOCKED` status;
- canonical `lock_sha256`;
- lock timestamp and every task freeze timestamp;
- campaign lock time not earlier than a task freeze;
- exact equality of lock and manifest fields;
- run configuration, data contract, promotion gate, and lineage hashes;
- unique task paths and expected task count;
- every locked task file hash and size;
- every task freeze's prediction hash;
- absence of actual-bearing artifacts.

The final `VERIFICATION_REPORT.json` contains
`prediction_lock_verification`. The final `VERIFICATION_SEAL.json` binds the
prediction lock file hash and records `prediction_lock_status=PASS`.

## Portable bundles

`verify-portable` first performs the complete PR #60 portable verification and
then re-runs prediction-lock verification against the relocated target run.

```bash
uv run loto-auto-campaign \
  verify-portable \
  --bundle exports/prospective-<run>.zip
```

The original absolute paths are not accessed. Prediction-lock file records are
run-relative, so they continue to resolve inside `payload/target` after
relocation.

## Idempotency and immutability

Calling the internal lock operation again on an unchanged valid lock returns the
existing lock without rewriting it. If any locked file changed, the existing
lock is invalid and is never silently replaced.

For non-prospective runs, prediction-lock verification is `NOT_APPLICABLE`.
Existing legacy verification seals for such runs are normalized as equivalent to
missing optional prediction fields and are not rewritten, preserving their bytes,
timestamp, and SHA-256.

## Timestamp boundary

The first schema records:

```text
timestamp_authority=LOCAL_SYSTEM_UTC
```

This proves the timestamp used by the local execution environment and binds it
into the lock hash. It is not an external trusted timestamp, digital signature,
remote transparency log, or proof against an authorized operator replacing the
entire evidence tree.

Formal operation should additionally publish the resulting lock SHA-256 and
portable bundle SHA-256 to an external append-only system before actual values
are available. That external publication is outside this change scope.
