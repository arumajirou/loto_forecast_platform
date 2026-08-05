# Sundial probabilistic provider v2

## Status

`PARTIALLY_VERIFIED / CONTRACT_IMPLEMENTED / REAL_RUNTIME_PENDING`

This change preserves the existing seven-position, one-step point forecast API while making the
Sundial generated samples the canonical provider output.

## Scope

PR-SD1 intentionally keeps the existing Loto7 geometry and `prediction_length=1`. Dynamic game
geometry and horizons 2 and 5 remain PR-SD2 work.

The provider now retains:

- raw samples with shape `[series, num_samples, prediction_length]`;
- sample mean, median, and population standard deviation;
- requested empirical quantiles derived from generated samples;
- a compatible one-step point prediction selected by `point_strategy`;
- exact snapshot, config, weight, and reviewed remote-code SHA-256 evidence.

## Fail-closed controls

- only `thuml/sundial-base-128m` at the pinned revision is accepted;
- the inspected resolved snapshot path is passed directly to `from_pretrained`;
- Hugging Face Hub and Transformers offline modes are enabled;
- unreviewed or changed remote-code files are rejected before model loading;
- only FP32 is accepted;
- a CUDA request fails when CUDA is unavailable or CPU execution is observed;
- invalid sample shapes, non-finite values, crossing quantiles, or point parity drift fail.

## Compatibility

`SundialProvider.predict()` continues to return a finite NumPy array with shape `[7]`.
`SundialProvider.predict_distribution()` returns the complete provider response and distribution.

## Verification boundary

Dependency-light focused tests exercise the contracts without downloading or loading the model.
Formal success still requires the pinned snapshot, isolated lock, real CPU smoke, real CUDA
execution, GPU PID and VRAM evidence, separate-process replay, Ruff, mypy, focused tests, full
pytest, and an actionable CI run.
