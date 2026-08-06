# Time-Series-Library provider contract v1

## Status

`PARTIALLY_VERIFIED / EIGHT_PINNED_CPU_MODELS_VERIFIED / FULL_MATRIX_PENDING`

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
- TimeFilter;
- TiDE.

Each lane has bounded fit, finite prediction/state checks, atomic artifact writes,
process exit, strict reload in a separate process, and prediction equality evidence.

## TiDE operations

- `tide_fit_save`;
- `tide_load_predict`.

Example:

```json
{
  "operation": "tide_fit_save",
  "model_name": "TiDE",
  "source_policy": "pinned",
  "seq_len": 8,
  "pred_len": 2,
  "channels": 3,
  "d_model": 8,
  "e_layers": 1,
  "tide_d_layers": 1,
  "tide_d_ff": 16,
  "tide_freq": "h",
  "dropout": 0.0,
  "train_steps": 3
}
```

The certified TiDE lane rejects encoder or decoder depths above one because the pinned
source constructs repeated blocks through list multiplication and therefore aliases the
same module instance. It also rejects non-zero dropout. Time marks are generated as
internal zero features; external covariate semantics remain outside this certification.

## Leakage boundary

Train, Validation, Holdout, and Prospective boundaries remain externally controlled.
Training materialization emits only Train and Validation artifacts. Holdout and
Prospective data are not opened by runtime smokes.

## Runtime boundary

The available runtime used Python 3.13.5 and Torch 2.10.0 CPU. The declared isolated
lane targets Torch 2.9.1. Exact target-environment, GPU, real-data accuracy, CI, and
merge readiness remain unclaimed.
