# Chronos-2 Data Contract

Each history row must contain:

- `draw_no`: unique, strictly increasing integer
- `draw_date`: parseable, strictly increasing timestamp
- every requested position column

Past covariates are index-aligned with history and must have exactly the same row count. Future covariates must contain exactly `prediction_length` rows and are copied only onto synthetic future timestamps. This prevents a future-covariate row from entering the historical context.

Lottery draw dates are mapped to an immutable synthetic daily timeline for model input. Source draw numbers, dates, and the compiled input are independently SHA-256 hashed. The original source rows are never overwritten.

Bingo5 uses eight position-specific ranges: 1-5, 6-10, 11-15, 16-20, 21-25, 26-30, 31-35, and 36-40.
