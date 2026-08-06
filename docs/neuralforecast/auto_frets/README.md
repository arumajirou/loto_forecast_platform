# Local NeuralForecast AutoFreTS Foundation

## Status

```text
PARTIALLY_VERIFIED
CONTRACT_AND_FACTORY_TESTS_PENDING_PUBLICATION
REAL_NEURALFORECAST_RUNTIME_PENDING
NOT_REGISTERED
ACCURACY_NOT_EVALUATED
```

## Scope

This package reimplements the reviewed FreTS architecture from
`thuml/Time-Series-Library` at revision
`4e938a1767106324dd753b2a44832bf870a0252e` as an inactive local
NeuralForecast `BaseModel` and `BaseAuto` extension.

PR #54 remains authoritative for the isolated native TSLib FreTS provider and its
pinned-source CPU evidence. This package does not import that provider at runtime.

## Semantic boundary

Version 1 is deliberately:

- position-univariate;
- exogenous-free;
- direct multi-step;
- point-loss-only;
- float32 FFT-only;
- channel-frequency mixing disabled;
- inactive and absent from shared catalogs and registries.

The local model preserves the pinned upstream architecture constants:

```text
embed_size=128
hidden_size=256
sparsity_threshold=0.01
scale=0.02
channel_independence="1"
```

The parameter-count contract is:

```text
66,432 + 32,768 * input_size + 257 * horizon
```

## Auto search space

The bounded Ray and Optuna search spaces cover:

- architecture profile, which resolves only the input window;
- training profile;
- learning rate;
- batch size;
- windows batch size;
- identity or robust scaling;
- random seed.

Frequency widths, sparsity, scale, channel policy, and precision are fixed. Nested Ray
and fractional GPU policies are outside this PR.

## Verification boundary

Focused tests use a controlled NeuralForecast interface boundary plus real local
PyTorch FFT execution. They are not real `neuralforecast==3.2.0`, Ray, Optuna, CPU
lifecycle, GPU, save/reload, OOF, Holdout, or Prospective evidence.

A later PR must add real package identity, fit, predict, save, load, replay, device,
GPU PID/UUID/VRAM, artifact sealing, and source identity before registration.
