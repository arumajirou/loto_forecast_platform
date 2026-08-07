# P7 Torch verification

`PARTIALLY_VERIFIED / LOCAL_TORCH_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

Executed locally:

- ten required Torch model identities retained;
- shared chunk, epoch, batch, seed, and Lightning trainer contract;
- `outer_workers=8` and serialized `max_gpu_jobs=1` policy;
- explicit runtime object resolution for scheduler, loss, likelihood, and metrics;
- position-local and global-sequence fake-runtime execution;
- CUDA parameter and prediction-device checks;
- GPU PID and VRAM/CUDA-memory evidence checks;
- CPU fallback rejection with durable evidence;
- requested/effective accelerator mismatch rejection;
- package-level Darts import failure retained for every requested model;
- per-model dependency and runtime failure isolation;
- prediction position, horizon, and finite-value checks;
- raw pandas frame immutability;
- focused tests: 11 passed;
- compileall, AST parse, YAML/JSON parse, and 100-character line inspection: PASS.

Not executed:

- installation or import of `darts==0.46.1` and its Torch extra;
- real NBEATS/NHiTS/TCN/TFT/DLinear/NLinear/TiDE/TSMixer/Transformer/RNN training;
- real PyTorch Lightning trainer execution;
- real CUDA parameter placement or prediction device;
- real GPU PID, VRAM peak, allocated, or reserved memory collection;
- real CPU-fallback rejection;
- checkpoint, best/last checkpoint, weights, or cross-device load certification;
- real OOF accuracy or baseline superiority.
