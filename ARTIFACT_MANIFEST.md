# Artifact manifest: NeuralForecast DB AutoModel campaign

Baseline: `arumajirou/loto_forecast_platform@e8c0821bd180db61028efe9ac323f8ea8a2d0399`

## Added

- `src/loto/neuralforecast/__init__.py`
- `src/loto/neuralforecast/db_automodel.py`
- `tests/test_neuralforecast_db_automodel.py`
- `configs/neuralforecast/numbers4_automodel_smoke.json`
- `scripts/run_numbers4_nf_automodels.sh`
- `docs/NEURALFORECAST_DB_AUTOMODEL.md`
- `docs/VERIFICATION_NEURALFORECAST_DB_AUTOMODEL.md`

## Modified

- `src/loto/cli.py`
- `src/loto/models/neuralforecast_adapter.py`
- `README.md`

## Generated runtime artifacts

A campaign creates:

- `input_panel.csv`
- `campaign_plan.json`
- `campaign_report.json`
- `models/<model-id>/run_report.json`
- `models/<model-id>/predictions.csv`
- `models/<model-id>/neuralforecast/` when model saving is enabled

No model weights, user databases, credentials, or generated run directories are
included in the source artifact.
