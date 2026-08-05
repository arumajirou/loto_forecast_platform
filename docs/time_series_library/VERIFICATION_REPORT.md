# Verification report

## Status

`PARTIALLY_VERIFIED / FIVE_PINNED_CPU_MODELS_VERIFIED / ISOLATED_LOCK_BLOCKED`

## Revisions

- project base: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- previous PR head: `5d83484a8f2cb2513bfda453921cc9bb4b3409fb`;
- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`.

## Existing certified models

DLinear, TSMixer, LightTS, and SegRNN remain certified. Their request schemas remain
accepted by the focused regression suite.

## FreTS source identity

Verified before fit and reload:

- `models/FreTS.py`: `ca4e0b648db42a1846b7a0a9a661a39177f47005`.

FreTS was selected over PAttn and WPMixer because it requires only PyTorch and NumPy,
while the alternatives introduce transformer/einops or wavelet decomposition lanes.

## FreTS runtime

- CPU construction: `PASS`;
- three bounded fit steps: `PASS`;
- losses remained finite and decreased from `0.5952046514` to `0.2215564847`;
- prediction shape `[2, 2, 3]`: `PASS`;
- finite prediction and state dictionary: `PASS`;
- parameter/input/output device CPU checks: `PASS`;
- parameter count `329090`: formula match;
- fit PID `9182` and load PID `9206` differ: `PASS`;
- strict state-dictionary reload: `PASS`;
- prediction SHA-256 equality: `PASS`;
- prediction SHA-256 `c192a26ecd44cf44b653d1dbf365a3afa5fb76092851e5187eb561e12b91e5cd`;
- `rtol=1e-8`, `atol=1e-8`: `PASS`;
- maximum absolute error `0.0`: `PASS`.

Six pinned-source matrix cases passed with channel mixing enabled and disabled,
1 through 7 channels, sequence lengths 4 through 24, and odd/even FFT geometries.

## Fail-closed checks

- wrong model/operation combination rejected: `PASS`;
- invalid channel-independence literal rejected: `PASS`;
- unverified source rejected: `PASS`;
- parameter-count formula checked at construction: `PASS`;
- tampered checkpoint geometry rejected: `PASS`;
- fixture and pinned certification separated: `PASS`.

## Focused validation

- Python compileall: `PASS`;
- focused pytest: `21 passed` in split runs;
- 100-character Python line policy: `PASS`;
- Ruff: `NOT_AVAILABLE_IN_EXECUTION_ENVIRONMENT`.

## Blocked

Direct GitHub clone remains blocked by DNS. `uv lock --offline` failed because
`einops==0.8.1` was absent from the local cache. No isolated `uv.lock` was created, and
root dependency files were not modified.

Earlier GitHub Actions runs remain `CI_BLOCKED_PRE_RUN`; this increment does not claim
CI success.

## Not claimed

- all-model import, construction, training, or inference;
- exact Torch 2.9.1 isolated runtime success;
- GPU PID, VRAM, device, or no-CPU-fallback certification;
- Foundation Model or Mamba execution;
- real lottery Hit@±1, MAE, MSE, or RMSE;
- baseline superiority;
- Holdout or Prospective results;
- merge readiness.
