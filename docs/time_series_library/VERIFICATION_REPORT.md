# Verification report

## Status

`PARTIALLY_VERIFIED / DLINEAR_AND_TSMIXER_CPU_VERIFIED / ISOLATED_LOCK_BLOCKED`

## Revisions

- project base: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- previous PR head: `3523e1b0a2514cbfe30579a21e1aec1f48e690a2`;
- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`.

## DLinear regression

The existing DLinear pinned-source and separate-process persistence contract remains
unchanged. Its legacy operations continue to pass the focused suite.

## TSMixer

Verified against `models/TSMixer.py` Git blob
`76884d467f17d64aa87d8e22cc9f0aa6231914cf`:

- pinned source identity: `VERIFIED`;
- CPU construction: `PASS`;
- three bounded fit steps: `PASS`;
- effective configuration persisted: `PASS`;
- prediction shape `[2, 2, 3]`: `PASS`;
- finite prediction and state dictionary: `PASS`;
- atomic save artifacts: `PASS`;
- fit and load process IDs differ: `PASS`;
- strict state-dictionary reload: `PASS`;
- reloaded prediction finite: `PASS`;
- prediction SHA-256 equality: `PASS`;
- `rtol=1e-8`, `atol=1e-8`: `PASS`;
- maximum absolute error `0.0`: `PASS`.

## Focused validation

- Python compileall: `PASS`;
- focused pytest: `9 passed`;
- 100-character Python line policy: `PASS`;
- Ruff: `NOT_AVAILABLE_IN_EXECUTION_ENVIRONMENT`;
- wrong model name rejected: `PASS`;
- unverified pinned TSMixer source rejected: `PASS`;
- fixture and certification policies separated: `PASS`.

## Candidate boundary

LightTS is deferred until chunk geometry and `d_model` reduction constraints are
formalized. SegRNN is deferred until `seg_len` divisibility and its Autoformer layer
dependency are formalized.

Pinned source search still reports 41 model modules. DLinear and TSMixer are separately
CPU-certified; the remaining model runtime matrix is pending.

## Blocked

Direct GitHub clone remains blocked by DNS. `uv lock --offline` failed because
`einops==0.8.1` was absent from the local cache. No isolated `uv.lock` was created, and
root dependency files were not modified.

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
