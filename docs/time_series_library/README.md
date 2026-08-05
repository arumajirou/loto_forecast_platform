# Time-Series-Library provider contract v1

## Status

`PARTIALLY_VERIFIED / SIX_PINNED_CPU_MODELS_VERIFIED / FULL_MATRIX_PENDING`

This integration isolates `thuml/Time-Series-Library` at revision
`4e938a1767106324dd753b2a44832bf870a0252e` from the root runtime.

## Source policy

Provider requests default to `source_policy="pinned"`. Registered operations verify
upstream Git blob identities before import, construction, fit, or reload. A missing or
mismatched file fails closed. `source_policy="test_fixture"` is restricted to focused
contract tests and is never reported as upstream certification.

## Certified CPU models

- DLinear;
- TSMixer;
- LightTS;
- SegRNN;
- FreTS;
- SCINet.

Each passed construction, bounded fit, finite prediction/state checks, atomic artifact
writes, process exit, strict reload in a separate process, and prediction equality at
`rtol=1e-8`, `atol=1e-8`.

## Provider operations

- `discover`;
- `dlinear_fit_save` and `dlinear_load_predict`;
- `tsmixer_fit_save` and `tsmixer_load_predict`;
- `lightts_fit_save` and `lightts_load_predict`;
- `segrnn_fit_save` and `segrnn_load_predict`;
- `frets_fit_save` and `frets_load_predict`;
- `scinet_fit_save` and `scinet_load_predict`;
- `verify_roundtrip`.

SCINet request:

```json
{
  "operation": "scinet_fit_save",
  "model_name": "SCINet",
  "source_policy": "pinned",
  "seq_len": 12,
  "pred_len": 4,
  "channels": 3,
  "scinet_stacks": 2,
  "dropout": 0.0,
  "train_steps": 3
}
```

SCINet rejects sequences shorter than eight, stack counts outside one or two, and
non-zero dropout that the upstream implementation would silently ignore. The provider
records the full upstream output and emits only its final forecast horizon.

## Leakage boundary

Train, Validation, Holdout, and Prospective boundaries remain externally controlled.
Training materialization emits only Train and Validation artifacts. Holdout and
Prospective data are not opened by runtime smokes.

## Runtime boundary

The available runtime uses Python 3.13.5 and Torch 2.10.0 CPU. The declared isolated
lane targets Torch 2.9.1. Its lock remains blocked by network and offline-cache limits,
so exact target-environment certification is pending.

A model listed by discovery is not runtime-certified. GPU success additionally requires
actual CUDA device, process, VRAM, output, and no-CPU-fallback evidence.
