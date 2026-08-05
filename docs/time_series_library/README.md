# Time-Series-Library provider contract v1

## Status

`PARTIALLY_VERIFIED / SEVEN_PINNED_CPU_MODELS_VERIFIED / FULL_MATRIX_PENDING`

This integration isolates `thuml/Time-Series-Library` at revision
`4e938a1767106324dd753b2a44832bf870a0252e` from the root runtime.

## Source policy

Requests default to `source_policy="pinned"`. Registered operations verify every file
in their executable source closure before import, construction, fit, or reload.
`source_policy="test_fixture"` is restricted to focused tests and is never reported as
upstream certification.

## Certified CPU models

- DLinear;
- TSMixer;
- LightTS;
- SegRNN;
- FreTS;
- SCINet;
- TimeFilter.

Each lane has bounded fit, finite prediction/state checks, atomic artifact writes,
process exit, strict reload in a separate process, and prediction equality evidence.

## TimeFilter operations

- `timefilter_fit_save`;
- `timefilter_load_predict`.

Example:

```json
{
  "operation": "timefilter_fit_save",
  "model_name": "TimeFilter",
  "source_policy": "pinned",
  "seq_len": 8,
  "pred_len": 2,
  "channels": 3,
  "d_model": 8,
  "timefilter_patch_len": 2,
  "timefilter_n_heads": 2,
  "timefilter_d_ff": 16,
  "timefilter_alpha": 0.1,
  "timefilter_top_p": 0.5,
  "e_layers": 1,
  "dropout": 0.0,
  "train_steps": 3
}
```

TimeFilter rejects non-divisible patches, odd positional widths, incompatible head
counts, excessive positional token counts, and modified checkpoint graph geometry.

## Leakage boundary

Train, Validation, Holdout, and Prospective boundaries remain externally controlled.
Training materialization emits only Train and Validation artifacts. Holdout and
Prospective data are not opened by runtime smokes.

## Runtime boundary

The available runtime used Python 3.13.5 and Torch 2.10.0 CPU. The declared isolated
lane targets Torch 2.9.1. Exact target-environment, GPU, real-data accuracy, CI, and
merge readiness remain unclaimed.
