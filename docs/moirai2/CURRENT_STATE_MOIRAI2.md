# Current State: Moirai 2.0

Status: `PARTIALLY_VERIFIED / P0_P7_IMPLEMENTED / REAL_UNI2TS_RUNTIME_PENDING`

The isolated Contract v2 from PR #83 remains the stacked base. P7 now compiles past-only and
known-future covariates into the native GluonTS fields consumed by `Moirai2Forecast`:

- `past_feat_dynamic_real`: past-only features aligned to the target history;
- `feat_dynamic_real`: known-future features aligned to target history plus forecast horizon.

P7 also includes covariate dimensions in the 512-token budget, preserves calendar gaps, hashes
ordered feature matrices and the future tail, rejects target/covariate name collisions, and verifies
response identity in the adapter. A fake-boundary runner test proves the wiring without claiming a
real Uni2TS model load. Real supported-lane and CUDA13-experimental execution remain pending.
