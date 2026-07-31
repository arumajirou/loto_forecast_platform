# All Model Runtime Validation

`scripts/all_model_runtime_validation.py` runs catalog models through a lifecycle-oriented
runtime check and writes per-model evidence under `runs/all-model-runtime-validation/<run-id>/`.

The harness records real stage outcomes. It does not mark worker models as `PASS` unless a
model body or reloadable provider artifact is available and the reload/retrain checks pass.

Example:

```bash
uv run python scripts/all_model_runtime_validation.py \
  --catalog configs/model_catalog.json \
  --available-only \
  --models uniform,frequency,stats-croston,stats-tsb \
  --require-fit \
  --require-predict \
  --require-save \
  --require-load \
  --require-retrain \
  --require-property-validation \
  --verify-arguments \
  --parallel-cpu-models 4 \
  --parallel-gpu-models 1 \
  --cpus-per-trial 4 \
  --gpus-per-trial 0 \
  --max-vram-mib 14500 \
  --timeout 1800 \
  --resume \
  --output runs/all-model-runtime-validation
```
