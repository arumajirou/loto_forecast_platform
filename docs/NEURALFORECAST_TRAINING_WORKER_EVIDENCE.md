# NeuralForecast Training-Worker Evidence

## Status

`IMPLEMENTED / DEPENDENCY_LIGHT / REAL_GPU_EXECUTION_PENDING / DRAFT`

This change supplies the formal training evidence required by the database runtime
certification and verifier. It does not claim that the registered RTX 5070 Ti or a real
NeuralForecast 3.2.0 campaign has passed.

## Why this evidence is needed

A CUDA-capable driver process, a model that later predicts on CUDA, or a post-training
runtime snapshot does not prove where model training occurred. Formal certification must
observe the process that executes the Lightning training loop for the selected model.

NeuralForecast 3.2.0 performs the backend search and then fits the selected best
configuration again through `BaseAuto._fit_model`. The evidence mixin overrides only that
method, appends a Lightning callback, delegates to the installed NeuralForecast class, and
attaches the callback result to the fitted inner model. The final refit evidence therefore
travels with the exact model later saved and reloaded by runtime certification.

The same callback also runs inside Ray and Optuna search fits. Those observations are not
promoted merely because a trial ran; runtime certification consumes the evidence attached
to the final selected fit.

## Captured hooks

The callback must observe all of the following:

- `on_fit_start`;
- `on_train_start`;
- the first `on_train_batch_end`;
- `on_train_end`.

The first training-batch capture is sufficient to prove that a real batch executed and
avoids invoking `nvidia-smi` for every batch. The end hook records final peak-memory and
process evidence.

## GPU proof contract

When GPU execution is required, formal training proof requires all of these facts in the
same evidence record:

- the four training hooks were observed;
- the callback completed without a capture error;
- the Lightning root device or module device is CUDA;
- allocated, reserved, or peak CUDA memory is positive;
- `nvidia-smi` lists the exact callback process PID;
- the callback `worker_pid`, runtime snapshot PID, and GPU snapshot PID are identical;
- `cuda_execution_evidence=true`;
- `cpu_fallback=false`;
- no failed checks are present.

`torch.cuda.is_available()` alone is never formal proof. A legacy dictionary containing
only `formal_training_proof=true` and `cuda_execution_evidence=true` is rejected.

For a CPU campaign, the four hooks can establish formal training-process proof without
claiming CUDA execution. CPU evidence never satisfies `formal_training_cuda`.

## Database installation

The stable database campaign module and its dataclasses remain unchanged. After the
existing database persistence facade is installed, a second idempotent facade temporarily
replaces the requested class in `neuralforecast.auto` with a stable, pickle-addressable
training-evidence subclass during construction. The original class is restored in
`finally`.

The model is configured from the active database execution context with:

- backend;
- NeuralForecast model class name;
- database campaign model ID;
- effective GPU requirement.

The existing database facade already serializes same-process construction through an
`RLock`, so the temporary class replacement does not introduce parallel mutation inside a
worker process. Process-pool workers install the facade through normal package import.

## Durable consumption

After `NeuralForecast.fit`, the final inner model exposes both compatibility names:

```text
training_runtime_evidence
runtime_training_evidence
```

`runtime_certification.py` extracts this record and embeds it in
`runtime_certification.json`. The runtime verifier then requires the strict callback
contract before accepting GPU training. Inference evidence before save and after reload
remains separate; training proof cannot substitute for either inference phase.

## Failure behavior

Missing hooks, callback errors, CPU devices in a GPU campaign, zero VRAM, missing or
mismatched PIDs, malformed schema fields, and legacy unversioned records all fail closed.
A failed proof prevents `formal_cuda_training_evidence=true` and therefore prevents formal
GPU runtime certification.

Search-space evidence written by the earlier stacked PRs remains independent and durable
even if construction or training fails before a training evidence record can be attached.

## Validation boundary

Local tests use synthetic trainer, CUDA-memory, and `nvidia-smi` responses to validate the
contract. These tests are not hardware execution evidence. Formal success still requires a
real target-host CPU smoke followed by an RTX GPU smoke, complete save/load inference,
finite output and state, CUDA device, VRAM, GPU PID, and no CPU fallback.

Runtime certification is not an accuracy result. Hit@±1 remains the primary forecasting
metric, accompanied by MAE, MSE, RMSE, position-level and all-position Hit@±1, multiple-seed
mean, variance and worst value, plus Random, fixed, mean, median, last-value, frequency and
statistical baselines under chronological Train, Validation, Holdout and Prospective
boundaries.

## Deferred scope

This change does not:

- run the real NeuralForecast 3.2.0 CPU or GPU smoke;
- certify the RTX 5070 Ti;
- execute all 36 AutoModels;
- activate TPE, CMA-ES, Grid, ASHA, or another search policy automatically;
- claim accuracy improvement;
- select a champion;
- alter raw data or prediction locks;
- merge or release the stacked PRs.
