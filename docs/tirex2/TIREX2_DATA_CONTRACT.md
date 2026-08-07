# TiRex-2 data contract

- `target_columns`: unique ordered identities matching `GameGeometry.position_count`.
- `target_history`: finite target-major matrix with exact `context_length` width.
- `past_covariates`: optional feature-major matrix with `context_length` width.
- `future_covariates`: optional feature-major matrix with `prediction_length` width.
- Future covariates require `known_at_prediction_time=true`,
  `future_actual_dependency=false`, and source timestamps not later than issue time.
- Supported horizons are exactly 1, 2, and 5 for this first certification slice.
