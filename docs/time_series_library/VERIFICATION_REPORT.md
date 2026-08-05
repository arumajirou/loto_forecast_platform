# Verification report

## Status

`PARTIALLY_VERIFIED / SIX_PINNED_CPU_MODELS_VERIFIED / ISOLATED_LOCK_BLOCKED`

## Revisions

- project base: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- previous PR head: `a895e50e017ce1d430946b034e8435f4db31346d`;
- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`.

## Existing certified models

DLinear, TSMixer, LightTS, SegRNN, and FreTS remain certified. Their request schemas
passed the split focused regression suite.

## Candidate decision

PAttn was not selected because importing its pinned attention dependency requires the
missing `reformer_pytorch` package. WPMixer requires missing `pywt`. TimeFilter is
executable but has a wider four-file source and graph-mask contract. SCINet is a
single-file PyTorch lane and was selected first.

## SCINet source identity

- `models/SCINet.py`: `740d0f7d88e8a94aa7fe12c745f0876af7b0fc08`;
- SHA-256: `06dcae9cfce5d3dc09e8db9b537479421848ee678ffbd1d3ca0b5c335a1baf25`.

## SCINet runtime

- CPU construction: `PASS`;
- three bounded fit steps: `PASS`;
- finite losses `0.0958132371`, `0.0804666504`, `0.0676129088`;
- raw output shape `[2, 28, 3]`: `PASS`;
- zero-filled raw prefix: `PASS`;
- final forecast shape `[2, 4, 3]`: `PASS`;
- finite prediction and state dictionary: `PASS`;
- parameter count `11824`: formula match;
- fit PID `47332` and load PID `50903` differ: `PASS`;
- strict state-dictionary reload: `PASS`;
- prediction SHA-256 equality: `PASS`;
- prediction SHA-256 `116e418080dcb1657fc320e11c00c2a9efd1ce8db56166b282d383b4edd3df3e`;
- maximum absolute error `0.0`: `PASS`.

Six pinned-source geometry cases passed with stack modes one and two, sequence lengths
8 through 24, odd sequence lengths, one through seven channels, raw-output checks,
module-count checks, finite state, and exact parameter formulas.

## Fail-closed checks

- wrong model/operation combination rejected: `PASS`;
- `seq_len < 8` rejected: `PASS`;
- stack count outside one or two rejected: `PASS`;
- silently ignored non-zero dropout rejected: `PASS`;
- unverified source rejected: `PASS`;
- tampered checkpoint geometry rejected: `PASS`;
- fixture and pinned certification separated: `PASS`.

## Focused validation

- provider regression: `6 passed`;
- FreTS regression: `7 passed`;
- SegRNN regression: `8 passed`;
- SCINet contract: `7 passed`;
- split focused total: `28 passed`;
- Python compileall: `PASS`;
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
