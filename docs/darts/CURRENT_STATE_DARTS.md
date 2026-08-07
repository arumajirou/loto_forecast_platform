# Darts isolated provider contract

**Status:** `PARTIALLY_VERIFIED / STATIC_AND_FAKE_RUNTIME_VERIFIED / REAL_DARTS_RUNTIME_BLOCKED`

## Frozen provenance

- base: `main`
- base SHA: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- branch: `feat/darts-forecasting-contract-v1`
- target: `darts==0.46.1`
- static upstream forecasting exports: 58

This branch is independent of NeuralForecast PRs #43/#45 and MLForecast PR #46.

## Implemented in this first increment

- separate `darts[notorch]` and `darts[torch]` environment manifests;
- strict Pydantic request/response protocol with unknown-field rejection;
- no-silent-drop argument classification;
- deterministic runtime discovery retaining optional dependency failures;
- versioned 58-name upstream forecasting export fixture;
- immutable GameGeometry panel validation;
- RangeIndex/draw-number position-local and multivariate adapter scaffolding;
- reproduction of the existing `RegressionEnsembleModel(NaiveDrift, ExponentialSmoothing)` route;
- focused tests using a fake Darts runtime.

## Explicit boundaries

No real Darts package was installed in the execution environment because its package registry did not expose `darts==0.46.1` and the GitHub tag fetch also failed. Therefore this branch does not claim:

- resolved `uv.lock` files;
- real Darts imports or executable-model count;
- real fit/predict/save/load certification;
- Torch or GPU execution;
- accuracy, Holdout or Prospective improvement.

The environment `pyproject.toml` files are committed without lockfiles. Lock generation remains `EXECUTION_PENDING` in a registry-capable environment.
