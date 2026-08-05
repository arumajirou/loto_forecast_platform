# P9 verification report

`PARTIALLY_VERIFIED / LOCAL_HISTORICAL_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

Executed locally:

- focused pytest: 12 passed;
- complete chronological origin generation;
- exact retrain boolean and integer-cadence schedules;
- prefit requirement for `retrain=false`;
- complete origin/target/position coverage;
- Hit@±1, position Hit@±1, all-position Hit@±1, MAE, MSE, RMSE;
- Darts backtest metric parity and mismatch failure;
- residual sign, order, shape, and numeric parity;
- optimized versus general historical forecast parity;
- no-silent-drop API argument classification;
- canonical policy and historical-ledger SHA-256;
- source DataFrame immutability;
- compileall, AST, YAML, and line-length checks.

Not executed:

- real `darts==0.46.1` installation;
- real `historical_forecasts()`, `backtest()`, or `residuals()` calls;
- optimized historical forecast runtime;
- real model retraining counts;
- real OOF, Holdout, Prospective, or Hit@±1 improvement;
- repository Ruff or full pytest.
