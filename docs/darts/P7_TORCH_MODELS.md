# P7 Torch model contract

`LOCAL_CONTRACT_VERIFIED / REAL_TORCH_RUNTIME_PENDING`

## Model identities

The matrix retains these ten Darts identities without hiding missing imports or optional
runtime failures:

- `NBEATSModel`
- `NHiTSModel`
- `TCNModel`
- `TFTModel`
- `DLinearModel`
- `NLinearModel`
- `TiDEModel`
- `TSMixerModel`
- `TransformerModel`
- `RNNModel`

## Shared training contract

Every model receives the same input/output chunk lengths, output shift, epochs, batch size,
optimizer arguments, random seed, checkpoint flags, and Lightning trainer request. Model-
specific arguments such as hidden size, layer widths, kernel size, attention heads, or RNN
cell identity remain explicit in each model entry and are validated against the constructor.

Scheduler, loss, likelihood, and Torch metric identities cannot be passed as raw strings to a
real model. They require an explicit runtime object resolver so the recorded identity and the
constructed Python object remain distinguishable.

## GPU contract

The default policy is `outer_workers=8` and `max_gpu_jobs=1`. A GPU request is successful only
when all of the following evidence is present:

- CUDA is available;
- the effective accelerator is GPU;
- model parameters are on a CUDA device;
- the prediction is on a CUDA device;
- process PID and GPU PID are recorded;
- VRAM before, peak, and after are recorded;
- CUDA allocated and reserved bytes are recorded.

`GPU available: True` alone is not accepted. A CPU fallback is retained as
`GPU_REQUESTED_BUT_CPU_FALLBACK`; with the default policy it fails as
`CPU_FALLBACK_REJECTED`. One model failure does not stop the remaining matrix.

## Series layouts

The contract supports position-local execution and one global model trained on the complete
position-series sequence. Predictions must have the exact position count and horizon and must
contain only finite values. The caller-owned pandas frame is not sorted, repaired, or mutated.

## Boundary

The tests use fake Torch models and fake runtime probes. They validate the orchestration,
argument, shape, device-evidence, and failure-ledger contracts. They do not certify Darts,
PyTorch Lightning, CUDA, model accuracy, checkpoints, or GPU memory behavior. Real checkpoint
and cross-device load certification remains part of P11.
