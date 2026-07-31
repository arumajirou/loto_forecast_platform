# AutoGluon-TimeSeries Provider Environment

Dedicated uv project for running the `autogluon-timeseries` position-series
worker outside the main application environment.

- Package: `autogluon.timeseries==1.5.0` (imports as `autogluon.timeseries`),
  pulling in `autogluon.core`/`autogluon.common`/`autogluon.features`/
  `autogluon.tabular`, plus `torch`, `lightning`, `gluonts`, `statsforecast`,
  `mlforecast`, `chronos-forecasting`, `transformers`, etc. License:
  Apache-2.0 (per PyPI metadata).
- Runtime API: `from autogluon.timeseries import TimeSeriesDataFrame,
  TimeSeriesPredictor`;
  `TimeSeriesPredictor(prediction_length=1, target="target",
  eval_metric="MAE", path=artifact_dir).fit(ts, presets="fast_training",
  time_limit=..., random_seed=...)`, then `predictor.predict(ts)`.
  `TimeSeriesPredictor.load(artifact_dir)` reloads a persisted predictor for
  reload-parity / retrain checks.
- Preset choice: `fast_training` (AutoGluon's `very_light` hyperparameter
  preset) is used for the smoke-level real fit. Verified empirically via
  `autogluon.timeseries.configs.hyperparameter_presets.get_hyperparameter_presets()`
  that `very_light` only trains `Naive`, `SeasonalNaive`, `ETS`, `Theta`,
  `RecursiveTabular`, `DirectTabular` (plus the `WeightedEnsemble` combiner) —
  no Chronos / deep-learning zero-shot component, no Hugging Face network
  download, CPU-only, real gradient/statistical fitting from scratch on the
  actual draw history in a few seconds. The default `medium_quality` preset
  (`light` hyperparameters) additionally trains `TemporalFusionTransformer`
  and `Chronos2` (small, fine-tuned) — heavier and network-dependent, so it is
  not used for the standard validation run, though it remains available via
  `params["presets"]` for a stronger fit if desired.
- Boundary: JSON request/response files only. The fitted `TimeSeriesPredictor`
  is never pickled or passed as a live Python object across the process
  boundary — it is persisted to disk (`artifact_dir`) by the fit subprocess
  and reloaded via `TimeSeriesPredictor.load()` by a separate subprocess
  invocation for reload-parity checks.
- Runtime status: this model trains from scratch on the real draw history in
  every invocation (no pretrained/zero-shot-only ceiling), so a genuine `PASS`
  is achievable given real save/load/reload-parity/retrain evidence.

Generated artifacts such as AutoGluon `path` directories, provider
request/response JSON files, stdout/stderr, GPU evidence, and model manifests
are not source artifacts and should not be committed.
