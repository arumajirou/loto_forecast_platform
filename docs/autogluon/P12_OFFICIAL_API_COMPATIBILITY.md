# AutoGluon 1.5.0 Official API Compatibility Audit

Status: `PARTIALLY_VERIFIED / STATIC_OFFICIAL_SOURCE_AUDIT`

## Scope

This phase compares the protocol-v2 provider against the official AutoGluon 1.5.0 public
API and rendered source for `TimeSeriesPredictor`. It does not replace real runtime
certification.

Official references:

- `https://auto.gluon.ai/stable/api/autogluon.timeseries.TimeSeriesPredictor.html`
- `https://auto.gluon.ai/stable/_modules/autogluon/timeseries/predictor.html`
- `https://auto.gluon.ai/stable/tutorials/timeseries/forecasting-indepth.html`
- `https://auto.gluon.ai/stable/tutorials/timeseries/forecasting-model-zoo.html`

## Verified static compatibility

The schema-v2 runner now validates generated constructor, fit, and predict keyword names
against the documented AutoGluon 1.5.0 public signatures before importing or executing
AutoGluon. Unsupported keyword names fail closed with
`AUTOGLUON_API_CONTRACT_MISMATCH`.

The HPO dictionary contract is also fail-closed at the actual schema-v2 runner boundary:

- required keys: `num_trials`, `scheduler`, and `searcher`;
- `num_trials` must be a positive integer;
- scheduler must be `local`;
- searcher must be `local_random`, `random`, `bayes`, or `auto`;
- string presets are limited to `auto` and `random`;
- unknown keys are rejected before the runtime provider is called.

The current bounded SeasonalNaive certification scenario uses `searcher="auto"`, which is
a documented 1.5.0 value. Official source states that this selects Bayesian optimization
for GluonTS-backed models and random search for other time-series models. Runtime evidence
is still required to prove the actual SeasonalNaive path in the pinned environment.

## Runtime boundary

This audit verifies names and documented argument shapes only. It does not prove package
installation, model construction, fit, prediction, save/load, optional dependency
availability, CPU/GPU execution, or output correctness. Those remain guarded runtime
certification gates.
