# StatsForecast test plan

## Focused local tests

1. strict Pydantic validation and no unknown fields;
2. 41 unique project inventory entries;
3. expected-negative `NaNModel` behavior;
4. immutable wide-to-long compilation;
5. integer, unique, monotonic, gap-free draw sequence;
6. chronological disjoint Train/Validation/Holdout splits;
7. Hit@±1, position Hit@±1, all-position Hit@±1, MAE, MSE, RMSE;
8. deterministic baseline behavior;
9. injected fake runtime construction, complete inventory, and output validation;
10. fail-closed argument ledger;
11. Prospective seal tamper detection;
12. runtime certifier missing-package bundle and fake save/load lifecycle.

## Runtime certification pending

- install exact StatsForecast distribution and record package hash;
- compare installed exports with the pinned inventory;
- run per-model constructor and minimum-data matrix;
- execute fit/predict/fit_predict/forecast/cross-validation;
- verify native and conformal interval schemas separately;
- perturb `X_df` to prove exogenous-variable usage;
- verify forward, fitted values, distributed paths, save/load/re-predict;
- run multiple seeds and preserve mean, variance, and worst values;
- keep Holdout and Prospective unopened until the formal gate.
