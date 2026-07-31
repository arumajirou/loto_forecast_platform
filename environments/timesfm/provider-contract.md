# TimesFM Provider Contract

Request JSON:

```json
{
  "model_id": "timesfm-2.5",
  "repo_id": "google/timesfm-2.5-200m-pytorch",
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
  "predictions": [],
  "prediction_shape": [7],
  "finite": true,
  "properties": {},
  "resource_evidence": {},
  "artifact_reference": {}
}
```

The provider must not pickle model objects across process boundaries.
