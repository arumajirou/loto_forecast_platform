# Handoff

## Recommended adoption PRs

Adopt the ledger incrementally rather than modifying this foundation PR:

1. `src/loto/orchestration/research.py`: emit dataset slices around rolling folds, model fit,
   tuning,
   prediction, and evaluation.
2. `scripts/run_formal_model_backtest.py`: emit formal fold, device-independent fit/predict, and
   leakage-check access events.
3. `src/loto/orchestration/pipeline.py`: emit vertical-slice stage transitions and state references.
4. `src/loto/coverage/runner.py` and `src/loto/coverage/auto_research.py`: emit bounded-search
   Train,
   Validation, and candidate-selection access.
5. NeuralForecast DB AutoModel runner paths: emit scaler/encoder/HPO state provenance and
   per-seed OOF
   access before runtime execution.
6. Actual scoring adoption: reference, but do not reimplement, the separate Prediction Lock and
   Actual
   Source contracts when creating READ_ACTUALS and SCORE events.

Each adoption PR should preserve Raw immutability, seal the ledger before result registration,
validate
it, store the report with the Run ID, and block downstream registration/promotion on errors. It
must not
interpret fixture PASS as campaign certification.

## Compatibility boundary

No root CLI entrypoint, configuration schema, model provider, Registry, API, workflow, database, or
runtime-certification contract changed. Consumers import only `loto.data_access_ledger`.
