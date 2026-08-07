# MLForecast strengthening specification

## Frozen provenance

The implementation targets only MLForecast `1.1.0`, tag `v1.1.0`, commit `a1609efddf8cf1a83510a50cd5487b66f32271c6`. Runtime version mismatch is fatal.

## Requirements

1. Core and Auto modes are explicit and separate.
2. Unknown configuration fields and model names fail closed.
3. Every additional input column is classified as static, known-future, or weight.
4. Input rows must already be chronologically ordered within each series.
5. Train/Holdout splitting is chronological and per-series.
6. Feature transforms, models, and Optuna trials fit only on Train.
7. Auto optimization defaults to `seed=1` and prioritizes Hit@±1.
8. Baselines use identical Holdout keys.
9. Model availability alone is not certification; save/load/re-predict must pass.
10. Prospective predictions are sealed before actuals with UTC time and SHA-256.
11. Raw input is copied without overwrite when execution starts from a file.

## Frozen Core API mapping

Constructor:

- `models`
- `freq`
- `lags`
- `lag_transforms`
- `date_features`
- `num_threads`
- `target_transforms`

Fit:

- `static_features`
- `dropna`
- `keep_last_n`
- `max_horizon` or `horizons`
- `prediction_intervals`
- `fitted`
- `as_numpy`
- `weight_col`
- `models_fit_kwargs`
- `validate_data`

Cross-validation additionally maps `n_windows`, `h`, `step_size`, `refit`, `input_size`, and `level`.

The schema maps the verified 1.1.0 constructor and fit arguments used by this runner and rejects unknown keys.

## Frozen Auto API mapping

Constructor:

- `models`
- `freq`
- `season_length`
- `fit_config`
- `num_threads`
- `reuse_cv_splits`

Fit:

- `n_windows`
- `h`
- `num_samples`
- `step_size`
- `input_size`
- `refit`
- `loss`
- key column names
- `study_kwargs`
- `optimize_kwargs`
- `fitted`
- `prediction_intervals`
- `weight_col`

`fit_config` supplies the explicit static-feature list and supported MLForecast fit arguments. The custom loss accepts the upstream keyword `train_df` and optional `weight_col`.

## Acceptance criteria

- Ruff format and lint pass.
- Python compilation and focused tests pass.
- Runtime imports exactly MLForecast 1.1.0.
- All eight AutoModels construct.
- Core Ridge and AutoRidge fit/predict/save/load smoke tests pass.
- Holdout and Prospective known-future keys exactly match expected horizons.
- Save/load predictions are finite and match within `rtol=1e-8`, `atol=1e-8`.
- Prospective seal verification succeeds.
