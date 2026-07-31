# TabPFN-TS Provider Environment

Dedicated uv project for running the TabPFN-TS foundation-candidate provider
outside the main application environment.

- Package: `tabpfn-time-series` (imports as `tabpfn_time_series`), pulling in
  `tabpfn` (the underlying in-context tabular foundation model).
- Weights: `Prior-Labs/TabPFN-v2-reg` on Hugging Face, file
  `tabpfn-v2-regressor.ckpt`. This is the ungated, commercially-licensed V2
  regressor checkpoint (Prior Labs License, Version 1.1, May 2025 — an
  Apache-2.0 derivative). The default `tabpfn_time_series` checkpoint
  (`Prior-Labs/tabpfn_3`) is deliberately NOT used here: it is gated behind an
  interactive browser license-acceptance flow and licensed
  non-commercial/non-production only. See `docs/providers/tabpfn-ts.md`
  section 2.1 for the full analysis.
- Runtime API: `from tabpfn_time_series import TabPFNTSPipeline, TabPFNMode`;
  `TabPFNTSPipeline(tabpfn_mode=TabPFNMode.LOCAL, tabpfn_model_config={"model_path": "tabpfn-v2-regressor.ckpt"}).predict_df(context_df, prediction_length=1)`.
  `context_df` requires `timestamp`, `target`, `item_id` columns.
- Boundary: JSON request/response files only. Do not pickle model, pipeline,
  or GluonTS objects across process boundaries.
- Runtime status: only report `ZERO_SHOT_PASS` after real local weight
  loading, a genuine 37-candidate one-hot-series prediction, finite shape
  `(37,)` validation, save/load reference, and subprocess reload parity.
  TabPFN is in-context-learning only (no gradient training step), so this
  model can never reach `PASS`.

Generated artifacts such as Hugging Face cache contents, provider request and
response JSON files, stdout/stderr, GPU evidence, and model manifests are not
source artifacts and should not be committed.
