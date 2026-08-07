# P7 Covariate Runtime Wiring

Status: `IMPLEMENTED / FAKE_RUNTIME_VERIFIED / REAL_UNI2TS_PENDING`.

## Upstream contract

Pinned Uni2TS source revision `cfd46d4510ed8896f263116f32928eede05b0a75` constructs
`Moirai2Forecast` with `feat_dynamic_real_dim` and `past_feat_dynamic_real_dim`. Its predictor uses:

- `feat_dynamic_real` for features available across context and prediction length;
- `past_feat_dynamic_real` for features available only in the past context.

Both feature classes become additional variates. Therefore the platform token budget includes target
context/prediction tokens, known-future context/prediction tokens, and past-only context tokens.

## Compilation contract

Feature names are sorted before matrix construction. Full-history inputs are sliced to the formal
context. Draw-sequence inputs retain one period per draw. Calendar-time inputs expand missing dates
to NaN so they remain aligned with the target calendar grid. Known-future tails are appended only
after the historical grid.

Durable response evidence contains names, shapes, full matrix SHA-256 values, future-tail SHA-256,
chronology status, availability status, and `actuals_used=false`.

## Fail-closed rules

- known-future names require exact `known_at_prediction_time` evidence;
- target columns cannot be reused as covariate names;
- past-only and known-future feature names must be disjoint;
- non-finite request values are rejected by Contract v2;
- matrix alignment or target-time mismatch is rejected;
- missing response hashes or changed feature identity is rejected by the adapter;
- covariate dimensions that exceed the 512-token limit are rejected before runtime.

## Certification boundary

The focused fake runner executes the complete project-side path into fake native classes and checks
GluonTS dataset fields plus model dimensions. Real Uni2TS transforms, model inference, quantile
outputs, CPU/GPU evidence, and predictive accuracy remain execution-pending.
