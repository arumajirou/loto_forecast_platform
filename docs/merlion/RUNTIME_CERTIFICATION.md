# Merlion Runtime Certification

## Current state

`EXECUTION_PENDING`

The repository contract and focused dependency-free tests are implemented. No real
Merlion package installation, import, model construction, fit, forecast, or save/load is
claimed by this change.

## Target-host sequence

1. Resolve and review `environments/merlion-core-py311/uv.lock`.
2. Run `uv sync --frozen` in the isolated environment.
3. Verify package version `2.0.4` and NumPy `<2.0`.
4. Run `identity` and dynamic `discover`.
5. Run separate-process certification for `Arima`, `ETS`, and `MSES`.
6. Verify prediction shape, finite values, standard-error contract, CPU evidence,
   no fallback, model manifest, and exact reload lineage.
7. Run Ruff, mypy, focused tests, and one full repository pytest only after the real
   runtime issues are resolved.

Formal status remains `EXECUTION_PENDING` until all three real model lifecycles pass.
