# P8 Foundation model contract

**Status:** `LOCAL_CONTRACT_VERIFIED / REAL_FOUNDATION_RUNTIME_PENDING`

## Models

- `Chronos2Model`
- `TimesFM2p5Model`
- `TiRexModel`
- `PatchTSTFMModel`

Zero-shot and fine-tuning are separate tracks. A zero-shot run must prove that
`enable_finetuning` was false, no optimizer step ran, and model parameters did not
change. A fine-tuning run must prove the inverse with at least one optimizer step.

## Revision and artifact identity

Every model requires an explicit Hugging Face model ID and immutable commit revision.
Default branches and tags are not accepted as formal provenance. Offline execution
requires a local directory, file count, total byte size, and a portable SHA-256
manifest. A requested revision that resolves to another revision fails as
`FOUNDATION_REVISION_MISMATCH`.

`UNRESOLVED` in the example configuration is an intentional blocker. It must be
replaced by an immutable commit revision before execution.

## Capability contract

The expected Darts 0.46.1 capability matrix records Chronos2 as supporting past and
future covariates. TimesFM 2.5, TiRex, and PatchTST-FM reject covariates. All four retain
univariate, multivariate, multi-series, probabilistic, zero-shot, and fine-tuning
contracts. Runtime `supports_*` properties must match the expected matrix; drift is not
silently accepted.

TiRex requires explicit license acceptance. Full fine-tuning is rejected; partial
fine-tuning requires an `unfreeze` or `freeze` pattern and
`tirex_kwargs.backend=torch`.

## Input and output

`input_chunk_length` accepts a fixed integer or `(min, max)` tuple. Chronos2 is capped at
8192 input points and `output_chunk_length + output_chunk_shift <= 1024`. TimesFM 2.5 is
capped at 16384 input points. TiRex output plus shift is capped at 2048. Shifted output
cannot be combined with an autoregressive horizon.

Predictions must match the requested position and horizon shape and contain only finite
values. Probabilistic samples are reduced only for shape certification; the full raw
prediction remains a runtime artifact in a real execution environment.

## Device evidence

P8 reuses the P7 fail-closed device contract. CUDA parameter and prediction devices,
process PID, GPU PID, VRAM before/peak/after, and CUDA allocated/reserved memory are
required for a GPU success claim. CPU fallback remains a failure.
