# Chronos-2 isolated runtime

This environment pins `chronos-forecasting==2.3.1` independently from the repository root.
The lockfile is intentionally not fabricated in a network-blocked authoring environment.
On the target host, run:

```bash
cd /absolute/path/to/loto_forecast_platform/environments/chronos2-py313
uv lock --python 3.13 2>&1 | tee /absolute/path/to/logs/chronos2-uv-lock.log
uv sync --frozen --python 3.13 2>&1 | tee /absolute/path/to/logs/chronos2-uv-sync.log
```

A reviewed `uv.lock` and its SHA-256 are required before formal runtime certification.
