# Verification report

## Status

`PARTIALLY_VERIFIED / NINE_PINNED_CPU_MODELS_VERIFIED / ISOLATED_LOCK_BLOCKED`

## Revisions

- project base: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- previous PR head: `73c6a479c59078cf06a62cbe3d12ad6ca3cae4dd`;
- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`.

## FiLM source identity

- `models/FiLM.py`: `1240e37047f26b0fd905151f0b2671255b6ec045`;
- SHA-256: `866054afc57411ebaf47c270566c05302b19acf3a3663b0b86e9153e386d2dc6`.

The source identity was verified before import, construction, fit, and reload. A
separately modified source was rejected before construction with provider exit code 2.

## Formal FiLM CPU runtime

Configuration: sequence `8`, horizon `2`, channels `3`, one declared layer, no
dropout, fixed HiPPO order `256`, scales `[1, 2, 4]`, and one spectral mode.

- construction: `PASS`;
- three bounded fit steps: `PASS`;
- losses `0.0869368687`, `0.0763578936`, `0.0670729801`;
- prediction shape `[2, 2, 3]`: `PASS`;
- finite prediction/state: `PASS`;
- parameter count `393226`: formula match;
- parameter and buffer devices: `cpu`;
- fit PID `2542`, load PID `2570`: separate processes;
- strict state load: `PASS`;
- prediction SHA `8a5badde08d4e9d2daff169794232fe48303a72429eec4d821e357a5186b4b36`;
- maximum absolute roundtrip error `0.0`: `PASS`;
- Python `3.13.5`, Torch `2.10.0+cpu`, NumPy `2.3.5`, SciPy `1.17.0`.

Six real pinned-source geometry cases passed. Coverage includes sequence lengths 8 to
40, horizons 2 to 10, one to seven channels, one to five spectral modes, finite state,
exact HiPPO evaluation shapes, CPU devices, and exact parameter formulas.

## Focused validation

- FiLM contract and checkpoint tests: `9 passed`;
- TiDE regression: `7 passed`;
- split focused total: `16 passed`;
- compileall: `PASS`;
- 100-character Python line policy: `PASS`;
- generated JSON validation: `PASS`;
- Ruff: `NOT_AVAILABLE_IN_EXECUTION_ENVIRONMENT`.

Prior provider, FreTS, LightTS, SegRNN, SCINet, TimeFilter, and TSMixer evidence is
retained, but those suites were not rerun in this FiLM authoring stage.

## Blocked and unclaimed

- isolated Torch 2.9.1 lock: blocked by offline cache/network limits;
- FiLM GPU lane: not certified; CUDA-visible CPU requests are rejected;
- Koopa: deferred because construction opens the Train data provider;
- MICN and TimesNet: multi-file execution closures remain pending;
- PAttn: missing `reformer_pytorch`;
- WPMixer: missing `pywt` in the available execution environment;
- GitHub Actions: `CI_BLOCKED_PRE_RUN` from prior runs;
- GPU, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, baseline superiority, and merge
  readiness: not executed or not claimed.
