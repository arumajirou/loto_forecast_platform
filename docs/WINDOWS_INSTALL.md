# Windows installation

Use 7-Zip to extract the release. The package uses ASCII-only archive paths for portability.

```powershell
Set-Location -LiteralPath "C:\Users\bp00425\env\forecast\loto_forecast_platform_v3.0.1"
uv sync --frozen --extra dev
uv run pytest -q
```

AutoGluon is intentionally installed in a separate virtual environment because AutoGluon 1.4.0 requires `mlforecast<0.15`, while the main `full` environment requires `mlforecast>=1.0`.
