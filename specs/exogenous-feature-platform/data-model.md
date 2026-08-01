# Data Model

`FeatureSpec` records name, dtype, availability, source, and required status. `ForecastInput` contains history and historical/future/static exogenous frames plus feature, source, and protocol hashes. Analysis rows are keyed by model, fold, seed, condition, and feature group.
