# Darts evaluation, persistence, and prospective contract

**Status:** `LOCAL_CONTRACT_VERIFIED / REAL_DARTS_RUNTIME_PENDING`

## Chronological evaluation

When `evaluation.enabled=true`, the final `holdout_size` rows are removed before any
`TimeSeries`, model, transform, or baseline is fitted. The request must set
`horizon == holdout_size`; otherwise validation fails closed.

The primary metric is `Hit@±1`. The bundle also records position-wise Hit@±1,
all-position Hit@±1, MAE, MSE, and RMSE. Random, fixed, mean, median, last, frequency,
and seasonal-naive baselines use the same holdout rows. Random predictions are
reproducible from the request seed.

## Save/load certification

`persistence.verify_save_load=true` requires `save_model=true`. Every position model is
saved separately, loaded through its model class, and inferred again under the same
horizon and predict arguments. Certification requires matching shapes, finite values,
and numerical equality under the configured `rtol` and `atol`.

Failed certification remains in `runtime_certification.json`; the provider returns
`PERSISTENCE_FAILED` without discarding the evidence.

## Prospective sealing

Prospective mode fits on all supplied history and excludes actual values. The canonical
payload contains only `run_id`, predictions, and `actual_known=false`. Its SHA-256 and UTC
timestamp are stored in `prospective_seal.json`. Any prediction mutation invalidates the
seal.

Evaluation and prospective sealing are mutually exclusive in one request.

## Artifact bundle

Each execution writes request/response JSON and applicable metrics, baselines,
certification, and seal files. `ARTIFACT_MANIFEST.json` and portable `SHA256SUMS` cover
all preceding files. Raw input remains caller-owned and is not overwritten.

## Certification boundary

Unit tests use fake model and TimeSeries implementations. They verify the local contract,
not the Darts 0.46.1 runtime. Real import, fit, predict, save/load, Torch, CUDA, GPU PID,
VRAM, and CPU-fallback certification remain pending.
