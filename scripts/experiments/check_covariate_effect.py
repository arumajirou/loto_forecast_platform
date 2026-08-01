from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from autogluon.timeseries import (
    TimeSeriesDataFrame,
    TimeSeriesPredictor,
)


predictor_path = Path(sys.argv[1])
data_path = Path(sys.argv[2])

predictor = TimeSeriesPredictor.load(str(predictor_path))
data = TimeSeriesDataFrame.from_pickle(data_path)

h = predictor.prediction_length
history = data.slice_by_timestep(None, -h)
future = data.slice_by_timestep(-h, None)

known = future[predictor.known_covariates_names].copy()

tests = {
    "all_zero": {column: 0.0 for column in predictor.known_covariates_names},
    "extreme_positive": {column: 999.0 for column in predictor.known_covariates_names},
    "column_specific": {
        "day_of_week": 6.0,
        "month_of_year": 12.0,
        "day_of_month": 31.0,
        "day_of_year": 366.0,
        "days_since_previous_draw": 30.0,
    },
}

baseline = predictor.predict(
    history,
    known_covariates=known,
).to_data_frame()

numeric = list(baseline.select_dtypes(include="number").columns)

results = {}

for test_name, replacement_map in tests.items():
    modified = known.copy()

    for column, value in replacement_map.items():
        if column in modified.columns:
            modified[column] = float(value)

    prediction = predictor.predict(
        history,
        known_covariates=modified,
    ).to_data_frame()

    difference = baseline[numeric].subtract(prediction[numeric]).abs()

    results[test_name] = {
        "mean_abs_change": float(difference.to_numpy().mean()),
        "max_abs_change": float(difference.to_numpy().max()),
    }

print(json.dumps(results, indent=2))

max_change = max(result["max_abs_change"] for result in results.values())

if max_change == 0:
    raise RuntimeError("Chronos2 predictions did not react to any covariate perturbation")

print("COVARIATE_EFFECT=PASS")
