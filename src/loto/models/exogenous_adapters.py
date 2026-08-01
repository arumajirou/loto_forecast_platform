from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from loto.models.forecast_input import ForecastInput


@dataclass(frozen=True)
class ExogenousPayload:
    hist_exog_list: tuple[str, ...]
    futr_exog_list: tuple[str, ...]
    stat_exog_list: tuple[str, ...]
    history_df: pd.DataFrame
    futr_df: pd.DataFrame | None
    static_df: pd.DataFrame | None


def neuralforecast_payload(inp: ForecastInput) -> ExogenousPayload:
    hist = tuple(() if inp.historical_exogenous is None else inp.historical_exogenous.columns)
    futr = tuple(() if inp.future_exogenous is None else inp.future_exogenous.columns)
    stat = tuple(() if inp.static_exogenous is None else inp.static_exogenous.columns)
    return ExogenousPayload(
        hist, futr, stat, inp.history, inp.future_exogenous, inp.static_exogenous
    )


def mlforecast_fit_kwargs(inp: ForecastInput) -> dict[str, Any]:
    return {
        "static_features": []
        if inp.static_exogenous is None
        else list(inp.static_exogenous.columns),
    }


def mlforecast_predict_kwargs(inp: ForecastInput) -> dict[str, Any]:
    if inp.future_exogenous is None:
        return {}
    if inp.future_exogenous.empty:
        raise ValueError("future_exogenous is empty")
    return {"X_df": inp.future_exogenous}


def chronos2_predict_kwargs(inp: ForecastInput) -> dict[str, Any]:
    return {
        "context_df": inp.history,
        "future_df": inp.future_exogenous,
        "prediction_length": 1,
    }


def timesfm_covariates(inp: ForecastInput) -> dict[str, Any]:
    numeric: dict[str, list[float]] = {}
    categorical: dict[str, list[str]] = {}
    if inp.future_exogenous is not None:
        for column in inp.future_exogenous.columns:
            series = inp.future_exogenous[column]
            if pd.api.types.is_numeric_dtype(series):
                numeric[column] = series.astype(float).tolist()
            else:
                categorical[column] = series.astype(str).tolist()
    return {"dynamic_numerical_covariates": numeric, "dynamic_categorical_covariates": categorical}
