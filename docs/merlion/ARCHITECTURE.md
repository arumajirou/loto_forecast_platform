# Merlion Architecture

```text
root process (NumPy 2.x)
  -> strict Pydantic JSON request
  -> bounded subprocess adapter
  -> isolated CPython 3.11 / NumPy 1.x provider
  -> Merlion ModelFactory
  -> atomic response and hash-bound model artifact
```

The provider has no permission to alter raw data, Holdout data, Prospective actuals,
shared model catalogs, deployment state, or a model registry.

The first formal runtime lane is CPU-only and limited to `Arima`, `ETS`, and `MSES`.
Every model must pass train, forecast, save, process exit, trusted manifest verification,
new-process load, reforecast, finite-value checks, and prediction comparison.
