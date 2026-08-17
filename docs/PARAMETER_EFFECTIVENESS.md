# Cross-platform model parameter effectiveness validation

## Purpose

`loto.parameter_effectiveness` turns model/library argument checks into a reusable repository-owned experiment instead of a one-off PowerShell or shell script.

An argument is **not** considered effective merely because:

- it appears in `inspect.signature`,
- the constructor accepts it,
- the library does not raise an exception, or
- one fit happens to produce a different score.

A probe executes a control value and a treatment value with the **same seed and repeat**, repeats the pair across at least two seeds, verifies successful finite inference, and compares an explicitly declared observable effect surface.

This harness is Development/synthetic screening infrastructure. It does **not** consume project Holdout or Prospective actuals and it must not be used to claim Holdout/Prospective accuracy certification.

## Effect surfaces

| Surface | Meaning | Example |
|---|---|---|
| `acceptance` | argument is accepted by a real run | constructor/fit routing smoke |
| `trial_count` | optimization/search work changed | MLForecast `num_samples` |
| `history` | exposed effective history/window usage changed | MLForecast `input_size` routing telemetry |
| `prediction` | prediction bytes/shape-normalized SHA-256 changed | StatsForecast `season_length` |
| `metric` | Development/synthetic metric changed | Hit@±1 response to an argument |
| `runtime` | measured wall time changed | compute-oriented arguments |

Expected relations are `change`, `increase`, `decrease`, and `invariant`. A compute-only argument can therefore be tested for a runtime change while separately requiring prediction invariance in another probe.

## Verdicts

- `effective`: the declared relation matched on at least `min_match_fraction` of all eligible paired runs, with no failed pair.
- `accepted_no_observable_effect`: the argument was accepted but a requested change/increase/decrease produced no observable difference.
- `expectation_violated`: runs completed, but the observed relation contradicted the declared expectation.
- `inconclusive`: at least one paired run failed or could not expose the requested surface.
- `unsupported`: the selected adapter/model/surface cannot route the probe.
- `failed`: no paired run produced valid accepted finite outputs.

The result stores `pairs_total`, `pairs_eligible`, `pairs_matched`, `pairs_failed`, matched fraction, and numeric control/treatment mean, population standard deviation, min/max and conservative worst value when the surface is numeric.

## Built-in adapters

### MLForecast / AutoMLForecast

The MLForecast adapter supports the repository's Auto model family:

- `AutoLightGBM`
- `AutoXGBoost`
- `AutoCatboost`
- `AutoRandomForest`
- `AutoElasticNet`
- `AutoLasso`
- `AutoRidge`
- `AutoLinearRegression`

`AUTO` scope routes known `AutoMLForecast` constructor/fit arguments such as `num_samples`, `input_size`, `refit`, `n_windows`, `step_size`, `num_threads`, `reuse_cv_splits`, and `season_length`. `model_constructor` can be used for arguments accepted directly by an Auto model class.

The adapter records real Optuna trial count, best value, finite prediction output shape, prediction SHA-256, synthetic Development Hit@±1 and runtime. For example, `num_samples=1` versus `2` is only certified when the observed trial count increases across the paired seeds.

### StatsForecast

The StatsForecast adapter probes real model-constructor arguments. The model class is resolved from `statsforecast.models`, checked for routability, fit on deterministic synthetic Development data, and forecast through `StatsForecast.forecast`.

The adapter records finite output shape, prediction SHA-256, synthetic Development Hit@±1 and runtime. The committed smoke suite compares `SeasonalNaive(season_length=2)` with `SeasonalNaive(season_length=7)` and expects the predictions to change.

## Reusable JSON suite

See `examples/parameter_effectiveness/cross_platform_smoke.json`.

Run the same command shape on Windows and Linux:

```text
python -m loto.parameter_effectiveness.cli --spec examples/parameter_effectiveness/cross_platform_smoke.json --output artifacts/parameter-effectiveness/run-001
```

The output directory contains:

- `suite.json`
- `results.json`
- `summary.csv`
- `environment.json`
- `manifest.json`
- `SHA256SUMS`

`environment.json` records run ID, UTC timestamp, OS/platform, machine, Python version and executable. Every evidence file is hashed. The results explicitly record `holdout_evaluated=false` and `prospective_evaluated=false`.

## Adding another forecasting library

Implement the `ParameterProbeAdapter` protocol in `core.py`:

1. Give the adapter a stable `library` key.
2. `supports(spec)` must say whether the exact model/parameter/surface can be routed. Signature inspection is allowed here only as a routing check; it is not an effectiveness result.
3. `run(spec, value, seed, repeat)` must execute a real control/treatment-compatible model path and return `ProbeRunObservation`.
4. A successful actual-model observation must set `accepted=true`, `success=true`, verify finite values, store the real output shape, and provide prediction SHA-256 when predictions exist.
5. Put adapter-specific scalar telemetry into `observables` using the normalized keys `trial_count`, `history`, or `metric` when those surfaces are supported.
6. Register the adapter in a registry. The core engine then supplies pairing, repetitions, aggregation, verdicts, evidence and hashing without library-specific shell code.

This protocol is the extension point for NeuralForecast, Darts, sktime, Time-Series-Library, BasicTS, GluonTS, foundation-model providers, and future libraries. Each adapter should expose only effect surfaces it can actually observe; unsupported telemetry must remain unsupported rather than being guessed.

## Windows and Linux CI

`.github/workflows/parameter-effectiveness-ci.yml` runs the same focused package under `windows-latest` and `ubuntu-latest` with Python 3.13. The workflow intentionally installs only the focused validation dependencies and real MLForecast/StatsForecast adapters. It does **not** install the repository's `full` extra or Ray, avoiding an unrelated Windows Ray-wheel constraint.

The matrix runs focused Ruff, mypy, core unit tests, real adapter tests, and the committed JSON CLI smoke. Full repository pytest and heavyweight GPU/runtime certification remain separate final gates.

## Relationship to accuracy and runtime certification

Parameter effectiveness answers: **did changing this argument cause the declared observable behavior, repeatedly and portably?**

It does not by itself answer: **did this improve unbiased forecasting accuracy?** Accuracy claims still require chronological Train/Validation/Holdout/Prospective governance, OOF/multiple seeds, required baselines, Hit@±1 plus MAE/MSE/RMSE and position metrics, and prediction sealing where actuals are genuinely unknown.

Likewise, a parameter probe does not replace formal model runtime certification. Production/runtime certification must still validate load, input, inference, output shape, finite values, device, GPU PID/VRAM where relevant, and CPU fallback independently.
