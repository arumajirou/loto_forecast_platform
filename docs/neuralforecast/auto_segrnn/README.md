# Local NeuralForecast AutoSegRNN Foundation

## Status

```text
PARTIALLY_VERIFIED
CONTRACT_AND_FACTORY_TESTS_PASS
REAL_NEURALFORECAST_RUNTIME_PENDING
NOT_REGISTERED
ACCURACY_NOT_EVALUATED
```

## Purpose

This add-only package implements a local NeuralForecast `BaseModel` adaptation of SegRNN and a
`BaseAuto` wrapper that supports Ray dictionary search spaces and Optuna
define-by-run search spaces.
It does not change the installed NeuralForecast package and does not register
the model in the shared Auto Campaign or catalog.

## Provenance

- architecture source: `thuml/Time-Series-Library`
- pinned source revision: `4e938a1767106324dd753b2a44832bf870a0252e`
- source path: `models/SegRNN.py`
- upstream license: MIT
- paper: SegRNN, arXiv 2308.11200
- target runtime contract: `neuralforecast==3.2.0`

The implementation is adapted to NeuralForecast's `windows_batch` contract. It does not import the
TSLib provider at runtime and does not duplicate PR #54's isolated TSLib execution path.

## Supported contract

- position-univariate forecasting only;
- no future, historical, or static exogenous variables;
- direct multi-step output;
- point training and validation losses only;
- formal horizons 1, 2, and 5 supported by every architecture profile;
- exact input and horizon divisibility by segment length;
- even hidden size for position and channel embeddings;
- Ray and Optuna AutoModel configuration;
- model identity fixed to `nf-local-auto-segrnn`.

Probabilistic losses are deliberately rejected because adding the final observed value to arbitrary
distribution parameters would not be semantically valid without a separately
designed output adapter.

## Search space

- architecture profile: compact, balanced, wide;
- training profile: smoke, standard, extended;
- learning rate: `1e-5..1e-2` log-uniform;
- batch size: 16, 32, 64;
- windows batch size: 128, 256, 512;
- dropout: 0.0, 0.1, 0.2;
- scaler: identity or robust;
- random seed: integers 1 through 19.

CPU/GPU resources are not accepted as direct `cpus` or `gpus` arguments. NeuralForecast 3.2.0
requires `RayOptions(cpus=..., gpus=...)` for Ray execution.

## Data boundary

No Raw, Train, Validation, OOF, Holdout, Prospective, actual, prediction,
baseline, or promotion artifact is read or written by this foundation PR.
Runtime and predictive evaluation remain separate follow-ups.

## Validation boundary

Dependency-light tests validate strict contracts, horizon geometry, finite
forward output, exact state roundtrip, point-loss rejection, Ray/Optuna factory
construction, and stable class identities. They use controlled NeuralForecast
and Ray interface doubles and are not real framework runtime evidence.
