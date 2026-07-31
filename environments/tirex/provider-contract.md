# TiRex Provider Contract

Request JSON:

```json
{
  "schema_version": 1,
  "model_id": "tirex",
  "repo_id": "NX-AI/TiRex-2",
  "revision": "05e5b26db52bfb256f1ae1bdf785589850482de3",
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
  "repo_id": "NX-AI/TiRex-2",
  "predictions": [],
  "prediction_shape": [7],
  "finite": true,
  "properties": {
    "license": "apache-2.0",
    "weight_sha256": {},
    "config_sha256": ""
  },
  "gpu_evidence": {},
  "artifact_reference": {}
}
```

The provider constructs `tirex2.TimeseriesType` inputs inside the subprocess
from JSON history. It must reject partial snapshots and must not substitute
Chronos, TimesFM, or Moirai implementations.
