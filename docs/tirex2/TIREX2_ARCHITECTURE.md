# TiRex-2 Architecture

## Status

`PARTIALLY_VERIFIED / CONTRACT_AND_HERMETIC_TESTS_ONLY`

## Boundaries

```text
Contract v2 request
  -> strict Pydantic validation
  -> trusted pinned snapshot verification
  -> isolated tirex-2==0.1.1 provider process
  -> native [target, 9 quantiles, horizon] output
  -> shape/finite/monotonic/q0.5 validation
  -> response evidence
```

The implementation is isolated under TiRex-2-owned paths. Shared workers, catalogs, CLI,
root dependency files, workflows, Holdout, and Prospective paths are unchanged.

The two-process certifier launches the same immutable request twice and compares model identity,
snapshot identity, all nine quantiles, point forecasts, series identity, prediction index, device,
and provider PID. Real package and GPU execution remain pending.
