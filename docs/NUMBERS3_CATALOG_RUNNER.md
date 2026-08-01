# Numbers3 Catalog Runner

`scripts/run_numbers3_catalog_models.py` evaluates catalog position-series models on the three independent Numbers3 digit series using an expanding window. It saves metrics, fold predictions, next predictions and model artifacts when the worker exposes a serializable payload.

## Smoke

```bash
uv run python scripts/run_numbers3_catalog_models.py \
  --data runs/data-acquisition-all/numbers3/normalized/numbers3.csv \
  --models ridge-position,stats-naive,mlforecast-ridge \
  --test-draws 3 --min-train-draws 1000 --lags 20 \
  --device cpu --output runs/numbers3-catalog-smoke
```

## Full attempt

```bash
uv run python scripts/run_numbers3_catalog_models.py \
  --data runs/data-acquisition-all/numbers3/normalized/numbers3.csv \
  --models all --test-draws 30 --min-train-draws 1000 \
  --lags 20 --max-steps 300 --num-samples 5 \
  --device cuda --save-models --reload-models \
  --verify-reload-predictions \
  --output "runs/numbers3-catalog-all-$(date +%Y%m%d-%H%M%S)"
```

Candidate-space models are rejected instead of being falsely mapped to decimal digits. Provider models that do not expose a serializable fitted payload are marked accordingly in their manifest.
