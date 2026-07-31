# Granite TTM Provider Contract

The dedicated provider is invoked outside the main application environment:

```bash
uv run --project environments/granite-ttm python scripts/run_granite_ttm_provider.py --request request.json --response response.json
```

Request JSON:

```json
{
  "repo_id": "ibm-granite/granite-timeseries-ttm-r2",
  "local_files_only": true,
  "device": "cuda",
  "history": [{"draw_date": "2026-01-01", "n1": 1, "n2": 2, "n3": 3, "n4": 4, "n5": 5, "n6": 6, "n7": 7}]
}
```

Response JSON:

```json
{
  "status": "OK",
  "repo_id": "ibm-granite/granite-timeseries-ttm-r2",
  "snapshot_path": "/path/to/local/snapshot",
  "device": "cuda",
  "position_values": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
}
```

Failure response JSON:

```json
{
  "status": "ERROR",
  "error_type": "ImportError",
  "message": "cannot import name TinyTimeMixerForPrediction"
}
```
