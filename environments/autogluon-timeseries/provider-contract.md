# AutoGluon-TimeSeries Provider Contract

Request JSON:

```json
{
  "schema_version": 1,
  "model_id": "autogluon-timeseries",
  "mode": "fit_predict_save",
  "artifact_dir": "/abs/path/to/model/dir",
  "history": [],
  "presets": "fast_training",
  "time_limit": 120,
  "prediction_length": 1,
  "eval_metric": "MAE",
  "seed": 42,
  "device": "cpu"
}
```

`mode` is one of:

- `fit_predict_save` — fit a fresh `TimeSeriesPredictor` on `history`, save it
  to `artifact_dir` (created if missing), and predict.
- `load_predict` — load a previously-saved `TimeSeriesPredictor` from
  `artifact_dir` and predict against `history` (no fitting).

`history` records carry `n1..n7` (drawn numbers, 1-37) and `draw_date` for
each historical draw. The provider reshapes this into 7 long-format series —
`item_id=f"position-{i}"` for `i` in `1..7`, `timestamp=draw_date`,
`target=float(n_i)` — mirroring `canonical_to_long()` in
`src/loto/models/workers.py`. It builds a `TimeSeriesDataFrame`, calls
`TimeSeriesPredictor.fit()`/`.load()` and `.predict()`, and returns the 7 raw
`mean` forecast values in `item_id` order `position-1..position-7` as
`predictions`. The platform-side caller normalizes these into valid candidate
probabilities via `normalize_worker_predictions()` — the provider itself does
not normalize.

Response JSON:

```json
{
  "status": "OK",
  "schema_version": 1,
  "provider_version": 1,
  "mode": "fit_predict_save",
  "predictions": [0, 0, 0, 0, 0, 0, 0],
  "prediction_shape": [7],
  "finite": true,
  "properties": {
    "library": "autogluon.timeseries",
    "package": "autogluon.timeseries",
    "library_version": "1.5.0",
    "license": "Apache-2.0",
    "presets": "fast_training",
    "time_limit": 120,
    "eval_metric": "MAE",
    "model_best": "WeightedEnsemble",
    "model_names": []
  },
  "gpu_evidence": {
    "requested_device": "cpu",
    "execution_device": "cpu",
    "cuda_available": false,
    "gpu_used": false,
    "gpu_certification": "NOT_CERTIFIED",
    "resource_certification": "CPU_ONLY_PASS"
  },
  "artifact_reference": {
    "artifact_dir": "/abs/path/to/model/dir"
  }
}
```

On failure, `status` is one of `ARTIFACT_MISSING` (load_predict against a
missing/incomplete `artifact_dir`), `PROVIDER_NOT_IMPLEMENTED` (unsupported
`mode`), or `ERROR` (uncaught exception, propagated with `error_type` and
`message`). The provider must not substitute a different model, return fixed
or uniform placeholder values, or report a fit as successful when the
underlying `TimeSeriesPredictor.fit()` call did not genuinely complete.
