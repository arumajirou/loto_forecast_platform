# Trusted vertical slice staged adoption

Status: `STACKED_ADOPTION / OPT_IN / PRE-COMMIT GOVERNANCE GATE`

This adoption lane implements the computational portion of
`src/loto/orchestration/pipeline.py` with runtime Data Access Ledger hooks, but it
does not execute Registry, PlatformRegistry, MLflow, release-bundle, ArtifactStore,
or event-publication commits.

## Why a staged implementation is required

The legacy `run_trusted_vertical_slice` function performs model evaluation,
forecast sealing, Registry writes, PlatformRegistry writes, MLflow recording,
release creation, artifact-store writes, and model registration in one function.
A post-run adapter could only validate after those side effects had already
occurred. This lane therefore separates computation and evidence validation from
downstream commit operations.

The audited legacy source is pinned to Git blob:

```text
98a323f91577f17292b474d566f9c1e58139c799
```

Any source drift blocks execution before the output directory is created.

## Runtime evidence

For both `uniform` and `frequency`, every backtest draw records:

```text
FIT_MODEL(TRAIN only)
PREDICT(target-free validation identity)
READ_ACTUALS(after prediction)
SCORE
```

The test row's `n1` through `n7` values are not accessed by the staged entrypoint
until both model predictions have been recorded. Model and position adapters only
receive the historical frame.

The final champion then records:

```text
FIT_MODEL(all historical TRAIN rows)
PREDICT(PROSPECTIVE_FEATURES)
LOCK_PREDICTION(local verified forecast seal)
```

The lock event documents only the existing local seal. It is not a trusted-time or
separate Prediction Lock certification claim.

## Preflight

Execution requires:

- a regular, non-symlink input CSV;
- an empty, non-symlink output path;
- an unchanged legacy pipeline Git blob;
- a seal secret of at least 16 bytes supplied through an environment variable;
- positive backtest and feature-window values.

## Artifacts

The staged lane writes local computation and governance artifacts, including:

- `canonical.csv` and `dataset_manifest.json`;
- `candidate_features.csv` and `feature_manifest.json`;
- `evaluation.json` with uniform/frequency metrics;
- `forecast.json` and `forecast.sealed.json`;
- `pipeline_data_access_ledger.json`;
- `pipeline_data_access_validation.json`;
- `pipeline_data_access_report.json`;
- `downstream_commit_plan.json`.

A successful return status is `READY_FOR_DOWNSTREAM_COMMIT`, not `SUCCEEDED` or
`REGISTERED`.

## Explicitly deferred operations

The following are listed in `downstream_commit_plan.json` but are not executed:

- `Registry.record_stage` and `Registry.record_forecast`;
- PlatformRegistry run, forecast, and model writes;
- `MlflowBridge.record_run`;
- release-bundle creation;
- `ArtifactStore.put_file`;
- event publication.

A later PR must consume a passing ledger and implement an idempotent downstream
commit transaction. This PR must not be used to claim registration, promotion,
trusted-time prediction locking, Actual Source verification, or production release.

## Command

```bash
export LOTO_FORECAST_SEAL_SECRET='replace-with-a-secret-of-at-least-16-bytes'
uv run python scripts/run_trusted_vertical_slice_with_ledger.py \
  --input /absolute/path/canonical_loto7.csv \
  --output /absolute/path/new-empty-run-directory \
  --backtest-draws 20 \
  --windows 10,30,100 \
  --seed 0
```
