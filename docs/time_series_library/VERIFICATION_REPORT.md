# Verification report

## Status

`PARTIALLY_VERIFIED / FOUR_PINNED_CPU_MODELS_VERIFIED / ISOLATED_LOCK_BLOCKED`

## Revisions

- project base: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- previous PR head: `4bf67c6d879d89d1ee089933ea8a541b9d98abbd`;
- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`.

## Existing certified models

DLinear, TSMixer, and LightTS remain unchanged by this increment. Their operation names
and request schemas remain accepted by the focused regression suite.

## SegRNN source identity

Verified before fit and reload:

- `models/SegRNN.py`: `afff1bc07dd14d227bbecdd36941d57f8aa8f63e`;
- `layers/Autoformer_EncDec.py`: `6fce4bcd6b3d3eb00e9bcf5931ed2ee301554f4a`.

A separately tampered Autoformer dependency was rejected with provider exit code 2.

## SegRNN runtime

- CPU construction: `PASS`;
- three bounded fit steps: `PASS`;
- segment geometry persisted: `PASS`;
- prediction shape `[2, 6, 3]`: `PASS`;
- finite prediction and state dictionary: `PASS`;
- parameter/input/output device CPU checks: `PASS`;
- parameter count `2713`: recorded;
- fit and load process IDs differ: `PASS`;
- strict state-dictionary reload: `PASS`;
- prediction SHA-256 equality: `PASS`;
- `rtol=1e-8`, `atol=1e-8`: `PASS`;
- maximum absolute error `0.0`: `PASS`.

Six real pinned-source geometry cases passed across 1, 3, 5, and 7 channels; segment
lengths 1, 2, 3, 4, 6, and 8; and `d_model` values 16 through 32.

## Fail-closed checks

- wrong model/operation combination rejected: `PASS`;
- odd `d_model` rejected: `PASS`;
- non-divisible input sequence rejected: `PASS`;
- non-divisible horizon rejected: `PASS`;
- unverified source rejected: `PASS`;
- tampered checkpoint geometry rejected: `PASS`;
- fixture and pinned certification separated: `PASS`.

## Focused validation

- Python compileall: `PASS`;
- focused pytest: `14 passed`;
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
