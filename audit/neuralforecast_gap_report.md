# NeuralForecast Official API Gap Report

- Generated: 2026-08-01T05:30:42.463420+00:00
- NeuralForecast version: 3.2.0
- Official fixed classes: 37
- Official Auto classes: 79
- Missing model references: 17
- Missing/unexposed core arguments: 39
- Missing/unexposed capabilities: 9

## Missing model references

- `SOFTSSharp` (fixed)
- `TimeLLM` (fixed)
- `XLinear` (fixed)
- `xLSTM` (fixed)
- `AutoSOFTSSharp` (auto)
- `AutoXLinear` (auto)
- `AutoxLSTM` (auto)
- `BaseAuto` (auto)
- `DistributionLoss` (auto)
- `MAE` (auto)
- `MQLoss` (auto)
- `MockTrial` (auto)
- `OptunaOptions` (auto)
- `RayOptions` (auto)
- `SOFTSSharp` (auto)
- `XLinear` (auto)
- `xLSTM` (auto)

## Missing or unexposed core arguments

- `NeuralForecast.__init__.local_scaler_type`
- `NeuralForecast.__init__.local_static_scaler_type`
- `NeuralForecast.cross_validation.data_kwargs`
- `NeuralForecast.cross_validation.id_col`
- `NeuralForecast.cross_validation.n_windows`
- `NeuralForecast.cross_validation.prediction_intervals`
- `NeuralForecast.cross_validation.quantiles`
- `NeuralForecast.cross_validation.refit`
- `NeuralForecast.cross_validation.static_df`
- `NeuralForecast.cross_validation.step_size`
- `NeuralForecast.cross_validation.target_col`
- `NeuralForecast.cross_validation.time_col`
- `NeuralForecast.cross_validation.use_fitted`
- `NeuralForecast.cross_validation.use_init_models`
- `NeuralForecast.cross_validation.verbose`
- `NeuralForecast.fit.distributed_config`
- `NeuralForecast.fit.id_col`
- `NeuralForecast.fit.prediction_intervals`
- `NeuralForecast.fit.static_df`
- `NeuralForecast.fit.target_col`
- `NeuralForecast.fit.time_col`
- `NeuralForecast.fit.use_init_models`
- `NeuralForecast.fit.val_df`
- `NeuralForecast.fit.verbose`
- `NeuralForecast.load.kwargs`
- `NeuralForecast.load.path`
- `NeuralForecast.load.verbose`
- `NeuralForecast.predict.data_kwargs`
- `NeuralForecast.predict.engine`
- `NeuralForecast.predict.futr_df`
- `NeuralForecast.predict.quantiles`
- `NeuralForecast.predict.static_df`
- `NeuralForecast.predict.verbose`
- `NeuralForecast.predict_insample.quantiles`
- `NeuralForecast.predict_insample.step_size`
- `NeuralForecast.save.model_index`
- `NeuralForecast.save.overwrite`
- `NeuralForecast.save.path`
- `NeuralForecast.save.save_dataset`

## Missing or unexposed capabilities

- `callbacks`
- `cross_validation`
- `futr_df`
- `optuna_options`
- `predict_insample`
- `prediction_intervals`
- `quantiles`
- `ray_options`
- `static_df`

## Important limitation

This report performs static reference detection. Every referenced result must be confirmed with a runtime contract test.
