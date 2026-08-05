from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def _values(prediction: Any) -> np.ndarray:
    raw = prediction.values() if hasattr(prediction, "values") else prediction
    array = np.asarray(raw, dtype=float).reshape(-1)
    if not np.isfinite(array).all():
        raise ValueError("prediction contains NaN or Inf")
    return array


def certify_model_roundtrip(
    *,
    model: Any,
    initial_prediction: Any,
    artifact_path: Path,
    horizon: int,
    predict_args: dict[str, Any],
    rtol: float,
    atol: float,
) -> dict[str, Any]:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    before = _values(initial_prediction)
    result: dict[str, Any] = {
        "artifact_path": str(artifact_path),
        "model_class": type(model).__name__,
        "status": "FAILED",
        "shape_before": list(before.shape),
        "shape_after": None,
        "finite_after_load": False,
        "prediction_equal": False,
    }
    try:
        model.save(str(artifact_path))
        loader = getattr(type(model), "load", None)
        if loader is None:
            raise TypeError(f"{type(model).__name__} does not expose classmethod load")
        loaded = loader(str(artifact_path))
        after = _values(loaded.predict(horizon, **predict_args))
        result["shape_after"] = list(after.shape)
        result["finite_after_load"] = bool(np.isfinite(after).all())
        result["prediction_equal"] = bool(
            before.shape == after.shape and np.allclose(before, after, rtol=rtol, atol=atol)
        )
        if not result["prediction_equal"]:
            raise ValueError("post-load predictions differ from pre-save predictions")
        result["status"] = "RUNTIME_CERTIFIED"
        return result
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        return result
