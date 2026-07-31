# TimesFM Provider Environment

Dedicated uv environment for `google/timesfm-2.5-200m-pytorch`.

The provider uses the official `timesfm` package with the PyTorch backend. The
main runtime process communicates with this environment through JSON files only.

Runtime contract:

- local Hugging Face snapshot only after acquisition
- `HF_HUB_OFFLINE=1` / `local_files_only=True` for validation
- seven Loto7 position series as independent TimesFM inputs
- `prediction_length=1`
- response includes point predictions, quantile shape, license, snapshot and
  weight/config hashes, resource evidence, and artifact reference
