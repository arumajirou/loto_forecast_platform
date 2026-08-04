# Verification: database-backed NeuralForecast AutoModels

## Scope

This change connects a constrained database-table reader to the registered
NeuralForecast AutoModel catalog and adds a Numbers4-compatible execution path.
The implementation baseline is repository commit
`e8c0821bd180db61028efe9ac323f8ea8a2d0399`.

## Status

| Check | Status | Evidence |
|---|---|---|
| SQLite table extraction | VERIFIED | Temporary `normalized_draws` table loaded and ordered |
| Numbers4 wide-to-long conversion | VERIFIED | Four equal-length series, targets constrained to 0-9 |
| AutoModel catalog resolution | VERIFIED | 36 registered `neuralforecast_auto` models in dry-run plan |
| Core argument wiring | VERIFIED | `models`, `freq`, both local scaler arguments covered by integration test |
| Fit argument wiring | VERIFIED | `df`, `val_size`, `use_init_models`, `verbose`, id/time/target columns covered |
| GPU queue bound | VERIFIED | Requested 8 workers resolves to 1 effective worker with `max_gpu_jobs=1` |
| NeuralForecast 3.2 resource contract | VERIFIED | Ray uses `RayOptions`; removed legacy `cpus`/`gpus` are not forwarded |
| Targeted tests | EXECUTED | 9 tests passed |
| Available-environment regression suite | PARTIALLY_VERIFIED | 650 passed, 2 skipped |
| Real AutoModel training in analysis sandbox | BLOCKED | `neuralforecast`, `ray`, `coreforecast`, and `utilsforecast` unavailable |
| Ruff | BLOCKED | Ruff executable unavailable and package registry inaccessible |

## Runtime boundary

A dry run verifies the database schema, input panel, model selection, Core/Fit
arguments, and queue policy without importing NeuralForecast. Actual training
requires the repository's full environment:

```bash
uv sync --extra full
```

The production command must first be run in `dry-run` mode, followed by `smoke`,
then `full`. The full campaign continues after individual model failures and
writes a separate traceback and report for each model.

## Leakage and reproducibility controls

- Input panel is exported before training.
- The panel SHA-256 is recorded in `campaign_plan.json`.
- Database credentials are masked in reports.
- Arbitrary SQL is rejected; only validated schema, table, and order identifiers
  are accepted.
- Seed, optimization backend, trial counts, resource limits, model list, and Core/Fit
  arguments are retained in the plan.
- Raw predictions and legal rounded/clipped Numbers4 predictions are both saved.
