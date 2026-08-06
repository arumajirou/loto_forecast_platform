from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

from .evaluation_contracts import OOFConfig


def _as_matrix(frame: pd.DataFrame, columns: Sequence[str]) -> np.ndarray:
    matrix = frame.loc[:, list(columns)].to_numpy(dtype=float).T
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("matrix must be two-dimensional and finite")
    return matrix


def _validate_history(history: pd.DataFrame, config: OOFConfig) -> None:
    required_columns = ("draw_no", "draw_date", *config.position_columns)
    missing = [name for name in required_columns if name not in history.columns]
    if missing:
        raise ValueError(f"history is missing required columns: {missing}")
    if len(history) < config.min_train_size + config.horizon:
        raise ValueError("history is too short")

    draw_numbers = pd.to_numeric(history["draw_no"], errors="raise").to_numpy(dtype=int)
    if len(set(draw_numbers.tolist())) != len(draw_numbers):
        raise ValueError("draw_no must be unique")
    draw_differences = np.diff(draw_numbers)
    if np.any(draw_differences <= 0):
        raise ValueError("draw_no must be strictly increasing")
    if config.require_gap_free_draw_no and np.any(draw_differences != 1):
        raise ValueError("draw_no must be gap-free")

    draw_dates = pd.to_datetime(history["draw_date"], errors="raise")
    if not draw_dates.is_monotonic_increasing or draw_dates.duplicated().any():
        raise ValueError("draw_date must be unique and strictly increasing")

    matrix = _as_matrix(history, config.position_columns)
    for index, name in enumerate(config.position_columns):
        lower, upper = config.position_ranges.get(
            name,
            (config.candidate_min, config.candidate_max),
        )
        values = matrix[index]
        if np.any(values < lower) or np.any(values > upper):
            raise ValueError(f"history values for {name} are outside [{lower}, {upper}]")
    if not config.allow_duplicates:
        for row_index, row in enumerate(matrix.T):
            if len(set(row.tolist())) != len(row):
                raise ValueError(f"history row {row_index} contains duplicates")
    if config.sort_policy == "ascending":
        for row_index, row in enumerate(matrix.T):
            if list(row) != sorted(row.tolist()):
                raise ValueError(f"history row {row_index} is not ascending")


def _position_bounds(config: OOFConfig, position: str) -> tuple[int, int]:
    return config.position_ranges.get(position, (config.candidate_min, config.candidate_max))


def _nearest_available(
    value: float,
    lower: int,
    upper: int,
    used: set[int],
) -> int:
    candidates = [candidate for candidate in range(lower, upper + 1) if candidate not in used]
    if not candidates:
        raise ValueError("no candidate remains after duplicate reconciliation")
    return min(candidates, key=lambda candidate: (abs(candidate - value), candidate))


def _reconcile_vector(values: np.ndarray, config: OOFConfig) -> np.ndarray:
    working = values.astype(float, copy=True)
    if config.sort_policy == "ascending" and not config.position_ranges:
        working = np.sort(working)
    output = np.empty(len(config.position_columns), dtype=float)
    used: set[int] = set()
    for position_index, position in enumerate(config.position_columns):
        lower, upper = _position_bounds(config, position)
        value = float(np.clip(working[position_index], lower, upper))
        if config.allow_duplicates:
            selected = int(np.rint(value))
            selected = min(max(selected, lower), upper)
        else:
            selected = _nearest_available(value, lower, upper, used)
            used.add(selected)
        output[position_index] = float(selected)
    if config.sort_policy == "ascending":
        output = np.sort(output)
    return output


def _postprocess(values: np.ndarray, config: OOFConfig) -> np.ndarray:
    if values.shape != (len(config.position_columns), config.horizon):
        raise ValueError("postprocessing received an unexpected prediction shape")
    output = np.empty_like(values, dtype=float)
    for horizon_index in range(config.horizon):
        output[:, horizon_index] = _reconcile_vector(
            values[:, horizon_index],
            config,
        )
    return output


def _random_baseline(history: pd.DataFrame, config: OOFConfig, seed: int) -> np.ndarray:
    del history
    rng = np.random.default_rng(seed)
    output = np.empty((len(config.position_columns), config.horizon), dtype=float)
    for horizon_index in range(config.horizon):
        if config.position_ranges:
            for position_index, position in enumerate(config.position_columns):
                lower, upper = _position_bounds(config, position)
                output[position_index, horizon_index] = rng.integers(lower, upper + 1)
        elif config.allow_duplicates:
            output[:, horizon_index] = rng.integers(
                config.candidate_min,
                config.candidate_max + 1,
                size=len(config.position_columns),
            )
        else:
            domain = np.arange(config.candidate_min, config.candidate_max + 1)
            output[:, horizon_index] = rng.choice(
                domain,
                size=len(config.position_columns),
                replace=False,
            )
    return _postprocess(output, config)


def _fixed_baseline(history: pd.DataFrame, config: OOFConfig) -> np.ndarray:
    del history
    if config.fixed_values is not None:
        values = np.asarray(config.fixed_values, dtype=float)
    else:
        if config.position_ranges:
            values = np.asarray(
                [
                    (sum(_position_bounds(config, position)) / 2.0)
                    for position in config.position_columns
                ],
                dtype=float,
            )
        else:
            values = np.linspace(
                config.candidate_min,
                config.candidate_max,
                num=len(config.position_columns) + 2,
            )[1:-1]
    return _postprocess(np.repeat(values[:, None], config.horizon, axis=1), config)


def _statistic_baseline(
    history: pd.DataFrame,
    config: OOFConfig,
    statistic: str,
) -> np.ndarray:
    matrix = _as_matrix(history, config.position_columns)
    if statistic == "mean":
        values = matrix.mean(axis=1)
    elif statistic == "median":
        values = np.median(matrix, axis=1)
    elif statistic == "last":
        values = matrix[:, -1]
    else:
        raise ValueError(f"unsupported statistic baseline: {statistic}")
    return _postprocess(np.repeat(values[:, None], config.horizon, axis=1), config)


def _frequency_baseline(history: pd.DataFrame, config: OOFConfig) -> np.ndarray:
    matrix = _as_matrix(history, config.position_columns)
    values: list[float] = []
    for position_index in range(matrix.shape[0]):
        counter = Counter(matrix[position_index].tolist())
        values.append(float(min(counter, key=lambda value: (-counter[value], value))))
    base = np.asarray(values, dtype=float)
    return _postprocess(np.repeat(base[:, None], config.horizon, axis=1), config)


def _seasonal_naive_baseline(history: pd.DataFrame, config: OOFConfig) -> np.ndarray:
    matrix = _as_matrix(history, config.position_columns)
    output = np.empty((matrix.shape[0], config.horizon), dtype=float)
    for horizon_index in range(config.horizon):
        offset = config.seasonal_period - (horizon_index % config.seasonal_period)
        source_index = max(0, matrix.shape[1] - offset)
        output[:, horizon_index] = matrix[:, source_index]
    return _postprocess(output, config)


def _ar1_baseline(history: pd.DataFrame, config: OOFConfig) -> np.ndarray:
    matrix = _as_matrix(history, config.position_columns)
    output = np.empty((matrix.shape[0], config.horizon), dtype=float)
    for position_index, values in enumerate(matrix):
        if len(values) < 3 or np.allclose(values[:-1], values[:-1].mean()):
            intercept = 0.0
            coefficient = 1.0
        else:
            design = np.column_stack([np.ones(len(values) - 1), values[:-1]])
            intercept, coefficient = np.linalg.lstsq(design, values[1:], rcond=None)[0]
        current = float(values[-1])
        for horizon_index in range(config.horizon):
            current = float(intercept + coefficient * current)
            output[position_index, horizon_index] = current
    return _postprocess(output, config)


Baseline = Callable[[pd.DataFrame, OOFConfig, int | None], np.ndarray]


def _baseline_registry() -> dict[str, Baseline]:
    return {
        "random": lambda history, config, seed: _random_baseline(
            history,
            config,
            int(seed),
        ),
        "fixed": lambda history, config, seed: _fixed_baseline(history, config),
        "mean": lambda history, config, seed: _statistic_baseline(
            history,
            config,
            "mean",
        ),
        "median": lambda history, config, seed: _statistic_baseline(
            history,
            config,
            "median",
        ),
        "last": lambda history, config, seed: _statistic_baseline(
            history,
            config,
            "last",
        ),
        "frequency": lambda history, config, seed: _frequency_baseline(history, config),
        "seasonal_naive": lambda history, config, seed: _seasonal_naive_baseline(
            history,
            config,
        ),
        "ar1": lambda history, config, seed: _ar1_baseline(history, config),
    }
