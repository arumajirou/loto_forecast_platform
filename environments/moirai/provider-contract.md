# Moirai Provider Contract

Request JSON:

```json
{
  "schema_version": 1,
  "model_id": "moirai",
  "repo_id": "Salesforce/moirai-2.0-R-small",
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
  "repo_id": "Salesforce/moirai-2.0-R-small",
  "predictions": [],
  "prediction_shape": [7],
  "finite": true,
  "properties": {
    "license": "cc-by-nc-4.0",
    "weight_sha256": {},
    "config_sha256": ""
  },
  "gpu_evidence": {},
  "artifact_reference": {}
}
```

The provider constructs GluonTS-compatible input inside the subprocess from
JSON history and must not pickle GluonTS dataset objects across process
boundaries.
