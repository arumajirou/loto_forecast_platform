from __future__ import annotations

from typing import Any

import numpy as np

from .runtime_policy import PredictionComparisonPolicy
from .runtime_prediction import prediction_summary


def compare_predictions(
    *,
    policy: PredictionComparisonPolicy,
    before_values: np.ndarray,
    after_values: np.ndarray,
    key_match: bool,
    rtol: float,
    atol: float,
    random_seed: int,
) -> tuple[bool, float | None, dict[str, Any]]:
    shape_match = before_values.shape == after_values.shape
    if policy == "stochastic":
        before_mean = np.mean(before_values, axis=0)
        after_mean = np.mean(after_values, axis=0)
        before_std = np.std(before_values, axis=0)
        after_std = np.std(after_values, axis=0)
        mean_match = bool(
            key_match
            and shape_match
            and np.allclose(before_mean, after_mean, rtol=rtol, atol=atol)
        )
        std_match = bool(
            key_match
            and shape_match
            and np.allclose(before_std, after_std, rtol=rtol, atol=atol)
        )
        maximum = (
            float(np.max(np.abs(before_mean - after_mean)))
            if key_match and shape_match and before_mean.size
            else None
        )
        details = {
            "policy": policy,
            "sample_count": int(before_values.shape[0]),
            "seeds": [random_seed + index for index in range(before_values.shape[0])],
            "mean_match": mean_match,
            "std_match": std_match,
            "max_abs_mean_diff": maximum,
            "max_abs_std_diff": (
                float(np.max(np.abs(before_std - after_std)))
                if key_match and shape_match and before_std.size
                else None
            ),
            "before": prediction_summary(before_values),
            "after": prediction_summary(after_values),
        }
        return bool(mean_match and std_match), maximum, details

    matched = bool(
        key_match
        and shape_match
        and np.allclose(before_values, after_values, rtol=rtol, atol=atol)
    )
    maximum = (
        float(np.max(np.abs(before_values - after_values)))
        if key_match and shape_match and before_values.size
        else None
    )
    return matched, maximum, {
        "policy": policy,
        "sample_count": 1,
        "seeds": [random_seed],
        "value_match": matched,
        "max_abs_diff": maximum,
    }
