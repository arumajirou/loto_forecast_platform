# Chronos-2 Provider Specification

## Supported operations

- `identity`: validate package/model identity without model loading.
- `predict`: execute zero-shot inference.
- `reference_reload`: validate the reference manifest and execute inference in a separate provider process when invoked through the runner.

## Layouts

- `position_local`: independent per-position inputs; `cross_learning=false`.
- `position_panel`: per-position inputs predicted jointly; `cross_learning=true`.
- `position_multivariate`: one item with all positions as targets; provider v2 requires `cross_learning=false` to avoid conflating two sharing mechanisms.

## Effective context

If the requested context exceeds available history, the provider records `NOT_APPLICABLE`, truncates to available history, and preserves the requested/effective pair in the argument ledger.

## Point semantics

In `chronos-forecasting==2.3.1`, the value returned by the `predictions` column is the trained 0.5 quantile. Provider v2 therefore stores it as both `point_forecast` and `median_forecast`. `mean_forecast` remains empty rather than falsely claiming an arithmetic mean.
