# Time-Series-Library provider contract v1

## Status

`PARTIALLY_VERIFIED / NINE_PINNED_CPU_MODELS_VERIFIED / FULL_MATRIX_PENDING`

This integration isolates `thuml/Time-Series-Library` at revision
`4e938a1767106324dd753b2a44832bf870a0252e` from the root runtime.

## Source policy

Requests default to `source_policy="pinned"`. Registered operations verify every
file in their executable source closure before import, construction, fit, or reload.
`source_policy="test_fixture"` is restricted to focused tests and is never reported
as upstream certification.

## Certified CPU models

- DLinear;
- TSMixer;
- LightTS;
- SegRNN;
- FreTS;
- SCINet;
- TimeFilter;
- TiDE;
- FiLM.

Each lane has bounded fit, finite prediction/state checks, atomic artifact writes,
process exit, strict reload in a separate process, and prediction equality evidence.

## FiLM operations

- `film_fit_save`;
- `film_load_predict`.

Example:

```json
{
  "operation": "film_fit_save",
  "model_name": "FiLM",
  "source_policy": "pinned",
  "seq_len": 8,
  "pred_len": 2,
  "channels": 3,
  "e_layers": 1,
  "dropout": 0.0,
  "train_steps": 3
}
```

FiLM requires `pred_len >= 2`, `seq_len >= 4 * pred_len`, a CPU-only interpreter,
and SciPy. CUDA-visible interpreters are rejected because the pinned source binds
HiPPO buffers to a module-global device at import time.

## Leakage boundary

Train, Validation, Holdout, and Prospective boundaries remain externally controlled.
Training materialization emits only Train and Validation artifacts. Holdout and
Prospective data are not opened by runtime smokes.

## Runtime boundary

The available runtime used Python 3.13.5, Torch 2.10.0+cpu, NumPy 2.3.5, and SciPy
1.17.0. The declared isolated lane targets Torch 2.9.1 and now declares
`scipy==1.17.0`. Exact target-environment, GPU, real-data accuracy, CI, and merge
readiness remain unclaimed.
