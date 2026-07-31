# TabPFN-TS Provider Contract

Request JSON:

```json
{
  "schema_version": 1,
  "model_id": "tabpfn-ts",
  "repo_id": "Prior-Labs/TabPFN-v2-reg",
  "revision": "4972a65a1b30806315c6f92499959ffbfc69a673",
  "weight_filename": "tabpfn-v2-regressor.ckpt",
  "snapshot_path": null,
  "local_files_only": true,
  "device": "cpu",
  "dtype": "float32",
  "history": [],
  "prediction_length": 1
}
```

Response JSON:

```json
{
  "status": "OK",
  "schema_version": 1,
  "provider_version": 1,
  "repo_id": "Prior-Labs/TabPFN-v2-reg",
  "predictions": [],
  "prediction_shape": [37],
  "finite": true,
  "properties": {
    "license": "Prior Labs License 1.1",
    "license_commercial_use": true,
    "license_attribution_required_on_distribution": true,
    "weight_sha256": {},
    "config_sha256": ""
  },
  "gpu_evidence": {},
  "artifact_reference": {}
}
```

`history` records carry `n1..n7` (drawn numbers, 1-37) and `draw_date` for
each historical draw. The provider constructs 37 independent one-hot series
internally from this history — one per candidate number 1-37, each row
`item_id=f"candidate-{candidate:02d}"`, `timestamp=draw_date`,
`target=float(candidate in {n1..n7})` — mirroring
`PositionSeriesWorker._candidate_series_frame()` in `src/loto/models/workers.py`.
It calls `TabPFNTSPipeline.predict_df()` once, keyed by `item_id`, and returns
the resulting 37 raw regression scores in candidate order 1-37 as
`predictions`. The platform-side caller normalizes these scores into valid
candidate probabilities (clip to non-negative, scale to sum 7.0) using
`normalize_worker_predictions()` — the provider itself does not normalize.

The provider must reject partial snapshots and must not substitute Chronos,
TiRex, TimesFM, or any other implementation. It must not silently fall back to
the gated `Prior-Labs/tabpfn_3` V3 checkpoint.
