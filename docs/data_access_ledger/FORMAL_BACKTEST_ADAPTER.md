# Formal backtest instrumented entrypoint

Status: `STACKED_ADOPTION / OPT_IN / RUNTIME_EVENT_HOOKS`

`run_formal_model_backtest_with_ledger.py` is a source-pinned entrypoint for the
existing formal walk-forward backtest. It imports the existing model, baseline,
metric, GPU-evidence, and leakage-check functions instead of copying model logic.
The legacy script Git blob must remain exactly
`fcf3aa745f209aedf1809a3fa2e32da66b4c2859`; any source change blocks execution
until the integration is reviewed again.

## Required lane

- resume is disabled and `--resume` is rejected;
- the output directory is empty and contains no symlink component;
- a regular canonical CSV and immutable `data_manifest.json` are required;
- the manifest canonical hash and row count must match fresh canonicalization;
- recursive data-file discovery is forbidden;
- one explicit seed is recorded for every selected model/fold.

## Runtime order

For each chronological fold, the entrypoint records:

1. `FIT_MODEL` after the model worker returns successfully;
2. `PREDICT` after shape, finite-value, and non-negative output checks;
3. `READ_ACTUALS` before leakage audit and target materialization;
4. `SCORE` after model metrics and all mandatory baseline metrics are persisted.

Target arrays are not materialized by the entrypoint before the prediction hook.
The canonical full frame is loaded for fold slicing, but model/provider calls receive
only `train_df`. Existing future-mutation checks remain unchanged and execute after
the prediction and actual-access boundary events.

## Fail-closed behavior

The run remains `BLOCKED` when:

- any fold fails, exits, is missing, or is not scored;
- leakage evidence is not exactly `PASS`;
- the source-pinned legacy script changes;
- resume, stale output, symlinks, ambiguous data discovery, manifest mismatch, or
  invalid canonical data is detected;
- foundation ledger validation returns `BLOCKED` or `INVALID`.

An `atexit` handler writes incomplete evidence when fail-fast or leakage detection
terminates the process. It never upgrades partial evidence to PASS.

## Artifacts

- `formal_backtest_data_access_ledger.json`
- `formal_backtest_data_access_validation.json`
- `formal_backtest_data_access_report.json`
- existing per-fold predictions, metrics, baseline metrics, resource evidence,
  leakage evidence, lifecycle, and fold manifests

## Non-claims

This PR does not execute a real backtest, open a designated Holdout split, perform
Prospective prediction locking, verify Actual Source provenance, certify a model
runtime/GPU lane, register artifacts, promote a model, or connect MLflow/PostgreSQL.
A static or synthetic test PASS is not a real campaign certification.
