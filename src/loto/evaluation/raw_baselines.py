"""Raw, no-postprocessing point baselines for common OOF evaluation."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

import numpy as np

from loto.evaluation.metric_registry import REQUIRED_BASELINE_IDS
from loto.game.geometry import GameGeometry, geometry_for


@dataclass(frozen=True, slots=True)
class RawBaselinePrediction:
    """One baseline point prediction made without target actuals."""

    baseline_id: str
    seed: int | None
    values: tuple[float, ...]

    @property
    def prediction_id(self) -> str:
        if self.seed is None:
            return self.baseline_id
        return f"{self.baseline_id}-seed{self.seed}"


def geometry_for_logical_game(game_id: str) -> GameGeometry:
    """Bridge platform logical IDs to the canonical geometry registry."""

    geometry_key = "mini" if game_id == "miniloto" else game_id
    return geometry_for(geometry_key)


def stable_target_seed(
    base_seed: int,
    game_id: str,
    target_draw_no: int,
) -> int:
    """Derive a schedule-independent RNG seed for one target."""

    payload = f"{base_seed}|{game_id}|{target_draw_no}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _validated_history(
    history: np.ndarray,
    geometry: GameGeometry,
) -> np.ndarray:
    matrix = np.asarray(history, dtype=float)

    if matrix.ndim != 2:
        raise ValueError("history must be two-dimensional")
    if matrix.shape[0] < 1:
        raise ValueError("history must contain at least one draw")
    if matrix.shape[1] != geometry.positions:
        raise ValueError(f"history has {matrix.shape[1]} positions; expected {geometry.positions}")
    if not np.isfinite(matrix).all():
        raise ValueError("history contains non-finite values")
    if not np.equal(matrix, np.rint(matrix)).all():
        raise ValueError("raw historical values must be integral")

    for row in matrix:
        geometry.validate_outcome(tuple(int(value) for value in row))

    return matrix


def _random_prediction(
    geometry: GameGeometry,
    *,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)

    if geometry.family == "digits":
        return rng.integers(
            geometry.value_min,
            geometry.value_max + 1,
            size=geometry.positions,
        ).astype("<f8")

    domain = np.arange(
        geometry.value_min,
        geometry.value_max + 1,
    )

    # A select-game random baseline samples one legal set uniformly.
    # Sorting is part of that baseline's generation semantics, not a
    # post-prediction reconciliation stage.
    return np.sort(
        rng.choice(
            domain,
            size=geometry.positions,
            replace=False,
        )
    ).astype("<f8")


def _fixed_prediction(geometry: GameGeometry) -> np.ndarray:
    if geometry.family == "digits":
        return np.full(
            geometry.positions,
            (geometry.value_min + geometry.value_max) / 2.0,
            dtype="<f8",
        )

    return np.linspace(
        geometry.value_min,
        geometry.value_max,
        num=geometry.positions + 2,
    )[1:-1].astype("<f8")


def _frequency_prediction(history: np.ndarray) -> np.ndarray:
    values: list[float] = []

    for position in range(history.shape[1]):
        counter = Counter(history[:, position].tolist())
        selected = min(
            counter,
            key=lambda value: (-counter[value], value),
        )
        values.append(float(selected))

    return np.asarray(values, dtype="<f8")


def _ar1_prediction(history: np.ndarray) -> np.ndarray:
    output: list[float] = []

    for position in range(history.shape[1]):
        values = np.asarray(history[:, position], dtype=float)

        if len(values) < 3 or np.allclose(
            values[:-1],
            values[:-1].mean(),
        ):
            prediction = float(values[-1])
        else:
            design = np.column_stack(
                [
                    np.ones(len(values) - 1),
                    values[:-1],
                ]
            )

            intercept, coefficient = np.linalg.lstsq(
                design,
                values[1:],
                rcond=None,
            )[0]

            prediction = float(intercept + coefficient * values[-1])

            if not np.isfinite(prediction):
                prediction = float(values[-1])

        output.append(prediction)

    return np.asarray(output, dtype="<f8")


def predict_raw_baselines(
    history: np.ndarray,
    *,
    game_id: str,
    target_draw_no: int,
    seeds: tuple[int, ...],
) -> tuple[RawBaselinePrediction, ...]:
    """Generate all required baselines without post-processing."""

    if not seeds:
        raise ValueError("seed inventory must not be empty")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seed inventory contains duplicates")

    geometry = geometry_for_logical_game(game_id)
    matrix = _validated_history(history, geometry)

    predictions: list[RawBaselinePrediction] = []

    for seed in seeds:
        values = _random_prediction(
            geometry,
            seed=stable_target_seed(
                seed,
                game_id,
                target_draw_no,
            ),
        )

        predictions.append(
            RawBaselinePrediction(
                baseline_id="random",
                seed=seed,
                values=tuple(float(value) for value in values),
            )
        )

    deterministic: dict[str, np.ndarray] = {
        "fixed": _fixed_prediction(geometry),
        "mean": matrix.mean(axis=0).astype("<f8"),
        "median": np.median(matrix, axis=0).astype("<f8"),
        "last": matrix[-1].astype("<f8"),
        "frequency": _frequency_prediction(matrix),
        "statistical_ar1": _ar1_prediction(matrix),
    }

    for baseline_id in REQUIRED_BASELINE_IDS:
        if baseline_id == "random":
            continue

        predictions.append(
            RawBaselinePrediction(
                baseline_id=baseline_id,
                seed=None,
                values=tuple(float(value) for value in deterministic[baseline_id]),
            )
        )

    actual_ids = {item.baseline_id for item in predictions}

    if actual_ids != set(REQUIRED_BASELINE_IDS):
        raise RuntimeError(f"baseline inventory mismatch: {sorted(actual_ids)}")

    return tuple(predictions)
