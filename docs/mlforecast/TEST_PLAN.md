# MLForecast test plan

## Fast local gates

1. `python -m compileall -q src tests`
2. `python -m ruff format --check src tests`
3. `python -m ruff check src tests`
4. `pytest -q tests/mlforecast`

## Contract tests

- exact version `1.1.0` accepted; other versions rejected;
- all eight AutoModel names accepted;
- unknown model and unknown fields rejected;
- unknown arguments rejected; 1.1.0 constructor and fit arguments accepted;
- malformed search spaces rejected;
- static and known-future feature sets are disjoint;
- unclassified feature columns rejected;
- changing static features rejected;
- duplicate and out-of-order rows rejected;
- future exogenous keys must exactly match the expected horizon;
- Hit@±1 miss count dominates MAE tie-breaking;
- baselines are deterministic at fixed seed.

## Runtime smoke gates

Using the verified wheel:

1. verify wheel SHA-256;
2. verify `importlib.metadata.version("mlforecast") == "1.1.0"`;
3. Core Ridge fit/predict;
4. Core save/load/re-predict;
5. AutoRidge with two Optuna trials;
6. Auto save/load/re-predict;
7. finite values and output shapes;
8. CPU process and thread configuration evidence.

## Formal campaign gates

- time-ordered Train/Validation/Holdout/Prospective;
- multiple seeds with mean, variance, and worst value;
- same folds and features for Core, Auto, NeuralForecast, statistical models, and baselines;
- Hit@±1 primary plus MAE, MSE, RMSE, position-wise, and all-position metrics;
- prediction sealing before actual disclosure;
- no best-seed-only promotion.
