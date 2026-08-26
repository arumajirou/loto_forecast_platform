"""Mirror the existing unified-campaign route admission without inventing new adapters."""

from __future__ import annotations

from .contracts import ModelInventoryRow

_CANDIDATE_LIBRARIES = {"sklearn", "lightgbm", "xgboost", "catboost"}
_POSITION_LIBRARIES = {
    "sklearn",
    "lightgbm",
    "statsforecast",
    "mlforecast",
    "neuralforecast",
    "neuralforecast_auto",
    "autogluon",
    "darts",
    "gluonts",
    "reservoirpy",
    "chronos",
    "timesfm",
    "transformers",
    "tirex",
    "uni2ts",
}
_CATALOG_CONTROLS = {"uniform", "frequency", "position-median", "position-modal"}


def known_route_reason(row: ModelInventoryRow) -> str | None:
    """Return a deterministic current-runner admission failure, if already knowable."""

    if row.source != "catalog":
        return None
    if row.task == "reconciliation":
        return "NON_STANDALONE_METHOD: reconciliation is not a standalone forecaster"
    if row.model_id in _CATALOG_CONTROLS:
        return "NOT_ROUTABLE: catalog control is represented by the mandatory baseline suite"
    if row.class_name == "AutoHINT":
        return "UNSUPPORTED_GAME: AutoHINT currently requires exactly seven coherent series"
    if row.class_name == "NaNModel":
        return "EXPECTED_NEGATIVE_CONTROL"
    if row.class_name == "SklearnModel":
        return "NOT_ROUTABLE: StatsForecast SklearnModel requires an explicit wrapped estimator"
    if row.task == "candidate":
        if row.library not in _CANDIDATE_LIBRARIES:
            return (
                "NOT_ROUTABLE: current unified candidate bridge supports only "
                f"{sorted(_CANDIDATE_LIBRARIES)}; observed={row.library}"
            )
        return None
    if row.task not in {"position", "position_series", "foundation"}:
        return f"NOT_ROUTABLE: current unified runner does not support task={row.task}"
    if row.library not in _POSITION_LIBRARIES:
        return f"NOT_ROUTABLE: no current PositionSeriesWorker route for library={row.library}"
    return None
