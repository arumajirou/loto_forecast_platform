# Local NeuralForecast AutoSCINet foundation

Status:

```text
PARTIALLY_VERIFIED
CONTRACT_AND_FACTORY_TESTS_PASS
REAL_RUNTIME_PENDING
NOT_REGISTERED
ACCURACY_NOT_EVALUATED
```

## Purpose

This package adapts the reviewed one-stack SCINet architecture to the
NeuralForecast `BaseModel` and `BaseAuto` contracts. It does not replace or
modify the native Time-Series-Library provider in Draft PR #54.

## Fixed architecture boundary

```text
position-univariate=true
stacks=1
tree_level=3
kernel_size=5
effective_dropout=0.0
SCIBlock count=15
CausalConvBlock count=60
point-loss-only=true
exogenous=false
```

For input window `L` and horizon `H`, the parameter-count contract is:

```text
720 + L * (L + H)
```

Input windows are rounded to a multiple of eight and bounded to 256.

## Search space

Only architecture profile, training budget, learning rate, batch size, window
batch size, scaler, and seed are searched. Tree depth, stack count, kernel,
dropout, and channel count are not search dimensions.

## Data and promotion boundary

No project data, actual value, OOF, Holdout, Prospective, prediction lock,
registry, catalog, API, Web UI, or promotion path is touched. Synthetic tensor
tests are not accuracy evidence.

A later runtime-certification PR must establish real
`neuralforecast==3.2.0` load, fit, predict, save, reload, replay, device,
GPU PID/UUID/VRAM, CPU fallback, and sealed artifact evidence.
