# P12 verification report

`PARTIALLY_VERIFIED / LOCAL_CROSS_LIBRARY_CONTRACT_VERIFIED / REAL_PROVIDERS_BLOCKED`

Executed locally:

- all eight provider tracks retained;
- Darts wrapper and standalone identity rules;
- pinned package/base revisions and SHA-256 validation;
- chronological fairness and leakage rejection;
- exact one canonical execution per base algorithm;
- CPU-fallback and incomplete GPU-evidence rejection;
- Hit@±1, position Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE;
- multi-seed mean, population variance, and worst values;
- duplicate, incomplete, and provider-specific forecast-key rejection;
- wrapper prediction and metric delta reporting without double counting;
- optional strict wrapper prediction parity;
- canonical-only champion selection with all seven baseline families;
- per-provider failure retention;
- report SHA-256 stability and tamper sensitivity;
- focused pytest: 14 passed;
- compileall and AST parsing: PASS;
- YAML parsing and 100-character line inspection: PASS.

Not executed:

- real Darts, NeuralForecast, MLForecast, StatsForecast, AutoGluon, or Foundation providers;
- real package-version compatibility checks;
- real common-fold predictions or wrapper parity;
- real multi-seed OOF, Holdout, or Prospective metrics;
- real GPU execution or memory evidence;
- real baseline improvement or champion selection.
