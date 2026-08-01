# Implementation status — 2026-08-01

## Completed in this sandbox

- Added `scripts/run_numbers3_catalog_models.py`.
- Generalized `PositionSeriesWorker` to infer/use dynamic position columns while preserving the seven-position Loto7 path.
- Added Numbers3 runner tests.
- Added a root-anchored transfer script that does not accidentally exclude `src/loto/data/`.
- Verified model-specific failure isolation: unsupported candidate-space models are recorded in `errors.csv` and do not stop other models.
- Verified Ridge position model expanding-window prediction, model pickle save, reload and prediction parity.

## Tests executed

- `tests/numbers3_catalog` plus target-exclusion tests: 8 passed.
- Synthetic Numbers3 smoke: `ridge-position` passed; `uniform` was correctly rejected as incompatible candidate-space logic.
- Full test collection was blocked because the uploaded transfer archive omitted `src/loto/data/` (10 tracked source files). The omission came from an unanchored `--exclude='data/'` rsync rule.

## Not claimed

- Full 84-model Numbers3 execution was not performed in the sandbox.
- GPU/checkpoint-dependent providers were not downloaded or executed.
- Repository-wide pytest was not certified due to the missing source package in the uploaded snapshot.
