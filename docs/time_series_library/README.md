# Time-Series-Library provider contract v1

## Status

`PARTIALLY_VERIFIED / DLINEAR_AND_TSMIXER_CPU_VERIFIED / FULL_MATRIX_PENDING`

This integration isolates `thuml/Time-Series-Library` at revision
`4e938a1767106324dd753b2a44832bf870a0252e` from the root runtime.

## Source policy

Provider requests default to `source_policy="pinned"`. DLinear and TSMixer operations
verify registered upstream Git blob identities before import, construction, fit, or
reload. A missing or mismatched file fails closed.

`source_policy="test_fixture"` is restricted to focused contract tests and is never
reported as upstream runtime certification.

## Certified CPU models

- DLinear;
- TSMixer.

Both passed construction, bounded fit, finite prediction and state checks, atomic
checkpoint/input/prediction writes, process exit, strict reload in a separate process,
and prediction equality within `rtol=1e-8`, `atol=1e-8`.

## Provider operations

- `discover`;
- `dlinear_fit_save`;
- `dlinear_load_predict`;
- `tsmixer_fit_save`;
- `tsmixer_load_predict`;
- `verify_roundtrip`.

TSMixer request example:

```json
{
  "operation": "tsmixer_fit_save",
  "model_name": "TSMixer",
  "source_policy": "pinned",
  "seq_len": 8,
  "pred_len": 2,
  "channels": 3,
  "d_model": 16,
  "dropout": 0.0,
  "e_layers": 2
}
```

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
