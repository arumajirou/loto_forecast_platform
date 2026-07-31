# Sundial Provider Contract

Request JSON:

```json
{
  "schema_version": 1,
  "model_id": "sundial",
  "repo_id": "thuml/sundial-base-128m",
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
  "repo_id": "thuml/sundial-base-128m",
  "predictions": [],
  "prediction_shape": [7],
  "finite": true,
  "properties": {
    "license": "apache-2.0",
    "weight_sha256": {},
    "config_sha256": "",
    "trust_remote_code": true,
    "remote_code_sha256": {}
  },
  "gpu_evidence": {},
  "artifact_reference": {}
}
```

The provider must use the Sundial remote-code implementation from the target
repository and must not route through Chronos, TimesFM, TiRex, or Moirai.
