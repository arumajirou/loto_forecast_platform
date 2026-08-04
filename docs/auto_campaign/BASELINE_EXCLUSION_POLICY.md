# Baseline Exclusion Policy

## Decision

The formal NeuralForecast AutoModel campaign contains only models dynamically
discovered from `neuralforecast.auto` that inherit from `BaseAuto`.

The following baseline families are excluded from execution, evaluation,
ranking, dashboards, reports and formal completion counts:

- Random
- Fixed
- Mean
- Median
- Last
- Frequency
- Naive
- HistoricAverage
- SeasonalNaive
- AutoARIMA
- AutoETS
- AutoTheta

## Reason

These methods produce fixed, repeated, naive or simple statistical values and
do not represent the AutoModel search surface required by this campaign.
Several methods may also be duplicates under the current data contract, such
as Last and Naive or Mean and HistoricAverage.

## Historical artifacts

Previously generated baseline artifacts and HTML files are retained only as
immutable audit evidence. They must not be included in new rankings or used to
claim formal all-AutoModel performance.

## Formal comparison scope

`NeuralForecast AutoModel versus NeuralForecast AutoModel`

The campaign manifest must contain:

```json
{
  "comparison_scope": {
    "baseline_models_included": false,
    "baseline_execution_enabled": false,
    "ranking_scope": "auto_models_only"
  }
}
```
