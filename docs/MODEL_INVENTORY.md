# Model Inventory Snapshot

## Status

`GENERATED_SNAPSHOT / NOT_CURRENT_BY_DEFAULT`

The table below is preserved as generated repository evidence from an earlier catalog snapshot. It must not be treated as the current model total without regenerating the catalog from the current code/revision.

`loto3 catalog --counts` is the intended runtime source for current catalog counts. A documentation table containing a number does not override the executable catalog.

| library | count in this snapshot | upstream/source note |
|---|---:|---|
| autogluon | 1 | — |
| builtin | 4 | — |
| catboost | 1 | — |
| darts | 1 | — |
| gluonts | 1 | — |
| hierarchicalforecast | 10 | github.com/Nixtla/hierarchicalforecast @ main:hierarchicalforecast/methods.py |
| lightgbm | 2 | — |
| mlforecast_auto | 8 | github.com/Nixtla/mlforecast @ main:mlforecast/auto.py |
| neuralforecast | 37 | github.com/Nixtla/neuralforecast @ main:neuralforecast/models/__init__.py |
| neuralforecast_auto | 36 | github.com/Nixtla/neuralforecast @ main:neuralforecast/auto.py |
| reservoirpy | 1 | — |
| skforecast | 1 | — |
| sklearn | 7 | — |
| sktime | 1 | — |
| statsforecast | 41 | github.com/Nixtla/statsforecast @ main:python/statsforecast/models.py |
| tsfm | 21 | huggingface.co/models?pipeline_tag=time-series-forecasting (snapshot note: 2026-07-30) |
| xgboost | 1 | — |
| **snapshot total** | **174** | historical/generated value; regenerate before a current claim |

This snapshot also recorded 21 TSFM entries as `UNPINNED`. Do not fabricate immutable revisions to make a catalog appear reproducible. Current pinning state must be queried from the current catalog/evidence.

For documentation-authority rules, see [DOCUMENTATION_CONTRACT.md](DOCUMENTATION_CONTRACT.md).
