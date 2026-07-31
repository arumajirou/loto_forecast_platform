# Granite TTM Provider Environment

Dedicated uv environment for `ibm-granite/granite-timeseries-ttm-r2`.

The provider runs out of process and exchanges JSON files with the main runtime
validation process. It does not pickle model objects across environments.

Primary package:

- `granite-tsfm`

Runtime behavior:

- load local Hugging Face snapshot with `local_files_only=True`
- use `tsfm_public.TinyTimeMixerForPrediction`
- treat the seven Loto7 positions as seven independent univariate batches
- left-pad context to the model `context_length` when the validation sample is shorter
- return seven finite position forecasts, snapshot reference, weight/config hashes,
  license metadata, and GPU evidence
