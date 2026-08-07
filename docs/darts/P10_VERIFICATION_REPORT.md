# P10 verification report

`PARTIALLY_VERIFIED / LOCAL_ENSEMBLE_CONFORMAL_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

Executed locally:

- four required public identities retained;
- chronological Train, calibration, and evaluation partition validation;
- pre-fitted global-model requirements;
- base-model availability and failure retention;
- output-chunk-shift and likelihood compatibility checks;
- constructor, fit, and predict no-silent-drop argument ledger;
- naive arithmetic-mean parity;
- stacking key completeness and evaluation-leakage rejection;
- quantile validation and non-crossing enforcement;
- interval coverage and width metrics;
- conformal/base median parity;
- matrix-level failure isolation;
- canonical SHA-256 tamper sensitivity;
- raw DataFrame immutability;
- focused pytest: 12 passed;
- compileall and AST parsing: PASS;
- YAML parsing and 100-character line inspection: PASS.

Not executed:

- real `darts==0.46.1` ensemble or conformal imports;
- real base-model fitting or prediction;
- real stacking-regressor training;
- real calibration historical forecasts;
- real empirical coverage or interval-width comparison;
- real OOF, Holdout, Prospective, GPU, save/load, or accuracy certification.
