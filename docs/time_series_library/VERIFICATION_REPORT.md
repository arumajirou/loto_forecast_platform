# Verification report

## Status

`PARTIALLY_VERIFIED / THREE_PINNED_CPU_MODELS_VERIFIED / ISOLATED_LOCK_BLOCKED`

## Revisions

- project base: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- previous PR head: `c67f6b0ce10b06661427a1b00c85b9c1e4643439`;
- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`.

## Regression boundary

The existing DLinear and TSMixer pinned-source, CPU-device, and separate-process
persistence contracts remain unchanged and pass the focused suite.

## LightTS

Verified against `models/LightTS.py` Git blob
`a2051e44d864ec4ec5e72e59660b98c30c93a902`:

- pinned source identity: `VERIFIED`;
- CPU construction and three bounded fit steps: `PASS`;
- parameter/input/output device checks: `PASS`;
- prediction shape `[2, 5, 3]`: `PASS`;
- finite prediction and state dictionary: `PASS`;
- requested chunk size 24, effective chunk size 5: recorded;
- sequence length 8 padded explicitly to 10: recorded and revalidated;
- fit and load process IDs differ: `PASS`;
- strict state-dictionary reload: `PASS`;
- prediction SHA-256 equality: `PASS`;
- `rtol=1e-8`, `atol=1e-8`: `PASS`;
- maximum absolute error `0.0`: `PASS`.

Six real-source geometry cases passed, covering no-padding and explicit-padding paths,
1/3/7 channels, horizons 1/3/5/7/24, and `d_model` 16/20/24. Implicit padding was
rejected as designed.

## Focused validation

- Python compileall: `PASS`;
- focused pytest: `16 passed`;
- 100-character Python line policy: `PASS`;
- Ruff: `NOT_AVAILABLE_IN_EXECUTION_ENVIRONMENT`;
- wrong model name rejected: `PASS`;
- `d_model` minimum and divisibility checks: `PASS`;
- implicit padding rejection: `PASS`;
- unverified pinned LightTS source rejected: `PASS`;
- tampered checkpoint geometry rejected: `PASS`;
- fixture and certification policies separated: `PASS`.

## Candidate boundary

SegRNN is deferred until `seg_len` divisibility, horizon geometry, and its external
layer-source identity are formalized. Pinned source search reports 41 model modules;
DLinear, TSMixer, and LightTS are separately CPU-certified.

## Blocked

Direct GitHub clone remains blocked by DNS. `uv lock --offline` failed because
`einops==0.8.1` was absent from local cache. No isolated `uv.lock` was created, and root
dependency files were not modified.

GitHub Actions runs continue to terminate before any recorded step or log blob. This is
classified as `CI_BLOCKED_PRE_RUN`, not a demonstrated code or test failure.

## Runtime boundary

The real model smokes used Python 3.13.5 and Torch 2.10.0 CPU. The declared isolated
lane targets Torch 2.9.1; execution in that exact environment remains pending.

## Not claimed

- all-model import, construction, training, or inference;
- GPU PID, VRAM, device, or no-CPU-fallback certification;
- Foundation Model or Mamba execution;
- real lottery Hit@±1, MAE, MSE, or RMSE;
- baseline superiority;
- Holdout or Prospective results;
- merge readiness.
