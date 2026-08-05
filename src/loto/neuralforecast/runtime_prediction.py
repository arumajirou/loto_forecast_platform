from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .runtime_policy import seed_runtime


def point_column(prediction: pd.DataFrame, alias: str) -> str:
    ignored = {"unique_id", "ds", "cutoff"}
    candidates = [column for column in prediction.columns if column not in ignored]
    if alias in candidates:
        return alias
    point_candidates = [
        column
        for column in candidates
        if not any(
            marker in str(column).lower() for marker in ("-lo-", "-hi-", "median", "quantile")
        )
    ]
    if point_candidates:
        return str(point_candidates[0])
    if not candidates:
        raise ValueError("NeuralForecast.predict returned no forecast value columns")
    return str(candidates[0])


def prediction_frame(
    prediction: pd.DataFrame,
    alias: str,
) -> tuple[pd.DataFrame, str, np.ndarray, bool]:
    key_columns = ["unique_id", "ds"]
    missing = [column for column in key_columns if column not in prediction]
    if missing:
        raise ValueError(f"prediction is missing keys: {missing}")
    point = point_column(prediction, alias)
    frame = prediction[[*key_columns, point]].copy()
    duplicate = bool(frame.duplicated(key_columns).any())
    frame = frame.sort_values(key_columns, kind="stable").reset_index(drop=True)
    return frame, point, frame[point].to_numpy(dtype=float), duplicate


def key_frames_match(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    if len(before) != len(after):
        return False
    try:
        pd.testing.assert_frame_equal(
            before[["unique_id", "ds"]],
            after[["unique_id", "ds"]],
            check_dtype=False,
            check_exact=True,
        )
    except AssertionError:
        return False
    return True


def collect_prediction_samples(
    forecaster: Any,
    *,
    alias: str,
    verbose: bool,
    random_seed: int,
    sample_count: int,
) -> tuple[list[pd.DataFrame], str, np.ndarray, bool, bool]:
    values: list[np.ndarray] = []
    point_columns: list[str] = []
    combined: list[pd.DataFrame] = []
    duplicate = False
    keys_consistent = True
    reference: pd.DataFrame | None = None
    for index in range(sample_count):
        seed_runtime(random_seed + index)
        frame, point, sample_values, sample_duplicate = prediction_frame(
            forecaster.predict(verbose=verbose),
            alias,
        )
        duplicate = duplicate or sample_duplicate
        point_columns.append(point)
        if reference is None:
            reference = frame
        else:
            keys_consistent = keys_consistent and key_frames_match(reference, frame)
        values.append(sample_values)
        sample = frame.rename(columns={point: "prediction"}).copy()
        sample.insert(0, "sample_index", index)
        sample.insert(1, "seed", random_seed + index)
        combined.append(sample)
    if len(set(point_columns)) != 1:
        raise ValueError(f"prediction point column changed across samples: {point_columns}")
    return combined, point_columns[0], np.vstack(values), duplicate, keys_consistent


def prediction_summary(values: np.ndarray) -> dict[str, Any]:
    return {
        "sample_count": int(values.shape[0]),
        "value_count": int(values.shape[1]),
        "mean": np.mean(values, axis=0).tolist(),
        "std": np.std(values, axis=0).tolist(),
        "minimum": np.min(values, axis=0).tolist(),
        "maximum": np.max(values, axis=0).tolist(),
    }
