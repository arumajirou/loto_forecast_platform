# MLForecast strengthening specification

## Requirements

1. MLForecast must be fixed to a runtime-certified version before feature expansion.
2. Core and Auto execution must use separate explicit modes.
3. Every accepted configuration field must map to a documented MLForecast 1.1.0 argument or a local evaluation contract.
4. Unknown configuration keys and model names must fail closed.
5. Train and Holdout rows must be separated chronologically per series.
6. Auto optimization must fit only on Train and use `seed=1` by default.
7. Hit@±1 must dominate the optimization objective; MAE is only a tie-breaker.
8. Candidate performance must be compared with deterministic baselines under identical Holdout rows.
9. Saved models must be loaded and re-predicted before runtime certification.
10. Prospective predictions must exclude actual values and be fixed with SHA-256 and UTC time.

## MLForecast Core mapping

`CoreConfig` maps to:

- constructor: `models`, `freq`, `lags`, `lag_transforms`, `date_features`, `num_threads`, `target_transforms`, `date_features_as_dummies`, `drop_auxiliary_columns`;
- fit: `static_features`, `dropna`, `keep_last_n`, `max_horizon`, `horizons`, `prediction_intervals`, `fitted`, `as_numpy`, `weight_col`, `validate_data`, `cache_train_df`;
- cross-validation: `n_windows`, `h`, `step_size`, `refit`, `input_size`, and the shared data arguments;
- predict: `h`, `level`, and derived holdout `X_df`;
- update: withheld actual rows after Holdout evaluation;
- save/load: complete fitted pipeline round trip.

## AutoMLForecast mapping

`AutoConfig` maps to:

- constructor: `models`, `freq`, `season_length`, `num_threads`, `reuse_cv_splits`;
- fit: `n_windows`, `h`, `num_samples`, `step_size`, `input_size`, `refit`, `loss`, `study_kwargs`, `optimize_kwargs`, `fitted`, `prediction_intervals`, `weight_col`;
- predict: `h`, `X_df`, `level`;
- save: one MLForecast bundle per optimized model.

Custom search spaces are declarative. Supported parameter types are integer, float, and categorical. The schema rejects malformed ranges and search spaces attached to unselected models.

## Acceptance criteria

- Ruff format and lint pass.
- Python compilation passes.
- Focused tests pass.
- All eight official AutoModel names are accepted and unknown names are rejected.
- Duplicate data and ordering violations are rejected.
- Hit@±1 and all-position Hit@±1 are emitted.
- Baseline predictions are deterministic for a fixed seed.
- Model save/load predictions match within `rtol=1e-8`, `atol=1e-8` in an installed MLForecast 1.1.0 runtime.
- Prospective seal verification succeeds.
