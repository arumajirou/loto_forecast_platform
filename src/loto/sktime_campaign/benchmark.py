from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from enum import StrEnum
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.sktime_campaign.matrix import (
    MODEL_SPECS,
    _distribution_versions,
    _load_class,
    _prediction_values,
)
from loto.sktime_campaign.protocol import ProviderStatus, SmokeModelId


class BaselineId(StrEnum):
    RANDOM_UNIFORM = "random_uniform"
    FIXED_MIDPOINT = "fixed_midpoint"
    MEAN = "mean"
    MEDIAN = "median"
    LAST = "last"
    FREQUENCY = "frequency"
    SEASONAL_NAIVE = "seasonal_naive"


FORMAL_BASELINES: tuple[BaselineId, ...] = tuple(BaselineId)
FORMAL_MODELS: tuple[SmokeModelId, ...] = tuple(MODEL_SPECS)


class ChronologicalSplit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train_rows: int = Field(ge=8)
    validation_rows: int = Field(ge=1)
    holdout_rows: int = Field(ge=1)

    @property
    def total_rows(self) -> int:
        return self.train_rows + self.validation_rows + self.holdout_rows


class GameMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1)
    draw_no: list[int] = Field(min_length=10)
    position_names: list[str] = Field(min_length=1)
    values: list[list[float]] = Field(min_length=10)
    legal_min: list[int] = Field(min_length=1)
    legal_max: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_geometry(self) -> GameMatrix:
        width = len(self.position_names)
        if len(set(self.position_names)) != width:
            raise ValueError("position_names must be unique")
        if len(self.draw_no) != len(self.values):
            raise ValueError("draw_no and values row counts differ")
        if len(self.legal_min) != width or len(self.legal_max) != width:
            raise ValueError("legal bounds must match position count")
        if any(high < low for low, high in zip(self.legal_min, self.legal_max, strict=True)):
            raise ValueError("legal_max must be >= legal_min")
        if self.draw_no != sorted(self.draw_no) or len(set(self.draw_no)) != len(self.draw_no):
            raise ValueError("draw_no must be strictly increasing and unique")
        if any(next_no != current + 1 for current, next_no in zip(self.draw_no, self.draw_no[1:])):
            raise ValueError("draw_no must be gap-free")
        for row_index, row in enumerate(self.values):
            if len(row) != width:
                raise ValueError(f"row {row_index} width does not match position_names")
            for column, value in enumerate(row):
                if not math.isfinite(value):
                    raise ValueError("values must be finite")
                if value < self.legal_min[column] or value > self.legal_max[column]:
                    raise ValueError("value outside legal position range")
        return self


class ValidationBenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["chronological_validation_benchmark"] = "chronological_validation_benchmark"
    output_dir: str = Field(min_length=1)
    environment_lane: Literal["classic-py312"] = "classic-py312"
    expected_sktime_version: Literal["1.0.1"] = "1.0.1"
    dataset: GameMatrix
    split: ChronologicalSplit
    baseline_ids: list[BaselineId] = Field(default_factory=lambda: list(FORMAL_BASELINES))
    model_ids: list[SmokeModelId] = Field(default_factory=lambda: list(FORMAL_MODELS))
    random_seeds: list[int] = Field(default_factory=lambda: [1, 2, 3], min_length=3)
    season_length: int = Field(default=7, ge=1)
    prediction_postprocess: Literal["round_clip"] = "round_clip"
    device: Literal["cpu"] = "cpu"

    @model_validator(mode="after")
    def validate_request(self) -> ValidationBenchmarkRequest:
        if self.split.total_rows != len(self.dataset.values):
            raise ValueError("split row total must equal dataset row count")
        if len(set(self.baseline_ids)) != len(self.baseline_ids):
            raise ValueError("baseline_ids must be unique")
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError("model_ids must be unique")
        if len(set(self.random_seeds)) != len(self.random_seeds):
            raise ValueError("random_seeds must be unique")
        if self.random_seeds != sorted(self.random_seeds):
            raise ValueError("random_seeds must be sorted")
        return self


def canonical_sha256(payload: Any) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def split_views(request: ValidationBenchmarkRequest) -> dict[str, Any]:
    values = np.asarray(request.dataset.values, dtype=float)
    train_end = request.split.train_rows
    validation_end = train_end + request.split.validation_rows
    return {
        "train": values[:train_end].copy(),
        "validation": values[train_end:validation_end].copy(),
        "holdout": values[validation_end:].copy(),
        "train_draw_no": request.dataset.draw_no[:train_end],
        "validation_draw_no": request.dataset.draw_no[train_end:validation_end],
        "holdout_draw_no": request.dataset.draw_no[validation_end:],
    }


def data_contract(request: ValidationBenchmarkRequest) -> dict[str, Any]:
    views = split_views(request)
    return {
        "schema_version": "1.0",
        "game_id": request.dataset.game_id,
        "position_names": request.dataset.position_names,
        "legal_min": request.dataset.legal_min,
        "legal_max": request.dataset.legal_max,
        "raw_rows": len(request.dataset.values),
        "raw_sha256": canonical_sha256(request.dataset.model_dump(mode="json")),
        "train_rows": request.split.train_rows,
        "validation_rows": request.split.validation_rows,
        "holdout_rows": request.split.holdout_rows,
        "train_draw_no": views["train_draw_no"],
        "validation_draw_no": views["validation_draw_no"],
        "holdout_draw_no": views["holdout_draw_no"],
        "train_values_sha256": canonical_sha256(views["train"].tolist()),
        "validation_values_sha256": canonical_sha256(views["validation"].tolist()),
        "holdout_values_sha256": canonical_sha256(views["holdout"].tolist()),
        "fit_scope": "TRAIN_ONLY",
        "evaluation_scope": "VALIDATION_ONLY",
        "holdout_access": "HASH_ONLY_NOT_SCORED",
    }


def postprocess_predictions(
    raw: np.ndarray,
    *,
    legal_min: list[int],
    legal_max: list[int],
) -> np.ndarray:
    if raw.ndim != 2:
        raise ValueError("prediction matrix must be two-dimensional")
    lower = np.asarray(legal_min, dtype=float)
    upper = np.asarray(legal_max, dtype=float)
    if raw.shape[1] != len(lower):
        raise ValueError("prediction width does not match legal bounds")
    if not np.isfinite(raw).all():
        raise ValueError("prediction matrix contains NaN or Inf")
    return np.clip(np.rint(raw), lower, upper)


def compute_metrics(
    actual: np.ndarray,
    prediction: np.ndarray,
    *,
    position_names: list[str],
) -> dict[str, Any]:
    if actual.shape != prediction.shape or actual.ndim != 2:
        raise ValueError("actual and prediction must have equal two-dimensional shape")
    if actual.shape[1] != len(position_names):
        raise ValueError("position_names length does not match matrix width")
    if not np.isfinite(actual).all() or not np.isfinite(prediction).all():
        raise ValueError("metrics require finite matrices")
    absolute_error = np.abs(prediction - actual)
    squared_error = np.square(prediction - actual)
    hit_matrix = absolute_error <= 1.0
    return {
        "hit_at_1": float(hit_matrix.mean()),
        "position_hit_at_1": {
            name: float(hit_matrix[:, index].mean()) for index, name in enumerate(position_names)
        },
        "all_position_hit_at_1": float(hit_matrix.all(axis=1).mean()),
        "mae": float(absolute_error.mean()),
        "mse": float(squared_error.mean()),
        "rmse": float(np.sqrt(squared_error.mean())),
        "n_draws": int(actual.shape[0]),
        "n_positions": int(actual.shape[1]),
    }


def _frequency_value(values: np.ndarray) -> float:
    counts = Counter(float(value) for value in values.tolist())
    highest = max(counts.values())
    return min(value for value, count in counts.items() if count == highest)


def baseline_predictions(
    baseline_id: BaselineId,
    *,
    train: np.ndarray,
    horizon: int,
    legal_min: list[int],
    legal_max: list[int],
    season_length: int,
    seed: int,
) -> np.ndarray:
    width = train.shape[1]
    if baseline_id is BaselineId.RANDOM_UNIFORM:
        rng = np.random.default_rng(seed)
        columns = [
            rng.integers(low, high + 1, size=horizon)
            for low, high in zip(legal_min, legal_max, strict=True)
        ]
        return np.column_stack(columns).astype(float)
    if baseline_id is BaselineId.FIXED_MIDPOINT:
        values = np.rint((np.asarray(legal_min) + np.asarray(legal_max)) / 2.0)
    elif baseline_id is BaselineId.MEAN:
        values = train.mean(axis=0)
    elif baseline_id is BaselineId.MEDIAN:
        values = np.median(train, axis=0)
    elif baseline_id is BaselineId.LAST:
        values = train[-1]
    elif baseline_id is BaselineId.FREQUENCY:
        values = np.asarray([_frequency_value(train[:, index]) for index in range(width)])
    elif baseline_id is BaselineId.SEASONAL_NAIVE:
        if train.shape[0] < season_length:
            raise ValueError("seasonal_naive requires at least one full season")
        seasonal = train[-season_length:]
        return np.vstack([seasonal[index % season_length] for index in range(horizon)])
    else:  # pragma: no cover
        raise ValueError(f"unsupported baseline: {baseline_id}")
    return np.tile(values, (horizon, 1)).astype(float)


def evaluate_baseline(
    baseline_id: BaselineId,
    *,
    train: np.ndarray,
    validation: np.ndarray,
    request: ValidationBenchmarkRequest,
    seed: int,
) -> dict[str, Any]:
    raw = baseline_predictions(
        baseline_id,
        train=train,
        horizon=validation.shape[0],
        legal_min=request.dataset.legal_min,
        legal_max=request.dataset.legal_max,
        season_length=request.season_length,
        seed=seed,
    )
    prediction = postprocess_predictions(
        raw,
        legal_min=request.dataset.legal_min,
        legal_max=request.dataset.legal_max,
    )
    return {
        "candidate_id": baseline_id.value,
        "candidate_kind": "baseline",
        "seed": seed,
        "status": ProviderStatus.PASS.value,
        "fit_scope": "TRAIN_ONLY",
        "evaluation_scope": "VALIDATION_ONLY",
        "raw_predictions": raw.tolist(),
        "predictions": prediction.tolist(),
        "metrics": compute_metrics(
            validation,
            prediction,
            position_names=request.dataset.position_names,
        ),
    }


def evaluate_sktime_model(
    model_id: SmokeModelId,
    *,
    train: np.ndarray,
    validation: np.ndarray,
    request: ValidationBenchmarkRequest,
) -> dict[str, Any]:
    spec = MODEL_SPECS[model_id]
    dependency_versions, missing = _distribution_versions(spec.required_distributions)
    base: dict[str, Any] = {
        "candidate_id": model_id.value,
        "candidate_kind": "sktime",
        "seed": 1,
        "class_path": spec.class_path,
        "constructor": spec.constructor,
        "required_distributions": list(spec.required_distributions),
        "dependency_versions": dependency_versions,
        "missing_dependencies": missing,
        "fit_scope": "TRAIN_ONLY",
        "evaluation_scope": "VALIDATION_ONLY",
        "position_status": {},
    }
    if missing:
        return {**base, "status": ProviderStatus.UNAVAILABLE.value}

    raw = np.empty_like(validation, dtype=float)
    for column, position_name in enumerate(request.dataset.position_names):
        try:
            estimator_class = _load_class(spec.class_path)
            estimator = estimator_class(**spec.constructor)
            target = train[:, column]
            import pandas as pd

            y = pd.Series(
                target,
                index=pd.RangeIndex(1, len(target) + 1, name="draw_no"),
                name=position_name,
                dtype=float,
            )
            fh = list(range(1, validation.shape[0] + 1))
            estimator.fit(y, fh=fh)
            prediction = estimator.predict(fh=fh)
            raw[:, column] = _prediction_values(
                prediction,
                expected_index=[len(y) + step for step in fh],
            )
            base["position_status"][position_name] = "PASS"
        except Exception as exc:
            base["position_status"][position_name] = "FAILED"
            return {
                **base,
                "status": ProviderStatus.FAILED.value,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }

    prediction = postprocess_predictions(
        raw,
        legal_min=request.dataset.legal_min,
        legal_max=request.dataset.legal_max,
    )
    return {
        **base,
        "status": ProviderStatus.PASS.value,
        "raw_predictions": raw.tolist(),
        "predictions": prediction.tolist(),
        "metrics": compute_metrics(
            validation,
            prediction,
            position_names=request.dataset.position_names,
        ),
    }


def aggregate_seed_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["candidate_id"]), []).append(row)
    aggregates: list[dict[str, Any]] = []
    metric_names = ("hit_at_1", "all_position_hit_at_1", "mae", "mse", "rmse")
    for candidate_id, candidate_rows in sorted(grouped.items()):
        passed = [row for row in candidate_rows if row.get("status") == "PASS"]
        aggregate: dict[str, Any] = {
            "candidate_id": candidate_id,
            "candidate_kind": candidate_rows[0]["candidate_kind"],
            "status": (
                "PASS"
                if len(passed) == len(candidate_rows)
                else ("PARTIAL" if passed else candidate_rows[0].get("status", "FAILED"))
            ),
            "seed_count": len(candidate_rows),
            "passed_seed_count": len(passed),
            "seeds": [row["seed"] for row in candidate_rows],
        }
        if passed:
            aggregate["metrics"] = {}
            for name in metric_names:
                values = np.asarray([row["metrics"][name] for row in passed], dtype=float)
                worst = float(values.min()) if "hit" in name else float(values.max())
                aggregate["metrics"][name] = {
                    "mean": float(values.mean()),
                    "variance": float(values.var()),
                    "worst": worst,
                }
        aggregates.append(aggregate)
    return aggregates


def build_leaderboard(aggregates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [row for row in aggregates if row.get("status") == "PASS" and "metrics" in row]
    return sorted(
        eligible,
        key=lambda row: (
            -row["metrics"]["hit_at_1"]["mean"],
            -row["metrics"]["all_position_hit_at_1"]["mean"],
            row["metrics"]["mae"]["mean"],
            row["candidate_id"],
        ),
    )


def run_validation_benchmark(request: ValidationBenchmarkRequest) -> dict[str, Any]:
    views = split_views(request)
    train = views["train"]
    validation = views["validation"]
    rows: list[dict[str, Any]] = []
    for baseline_id in request.baseline_ids:
        seeds = request.random_seeds if baseline_id is BaselineId.RANDOM_UNIFORM else [1]
        rows.extend(
            evaluate_baseline(
                baseline_id,
                train=train,
                validation=validation,
                request=request,
                seed=seed,
            )
            for seed in seeds
        )
    rows.extend(
        evaluate_sktime_model(
            model_id,
            train=train,
            validation=validation,
            request=request,
        )
        for model_id in request.model_ids
    )
    aggregates = aggregate_seed_results(rows)
    leaderboard = build_leaderboard(aggregates)
    pass_count = sum(row.get("status") == "PASS" for row in rows)
    overall = "PASS" if pass_count == len(rows) else ("PARTIAL" if pass_count else "FAILED")
    return {
        "schema_version": "1.0",
        "status": overall,
        "stage": "validation",
        "data_contract": data_contract(request),
        "actual_validation": validation.tolist(),
        "candidate_results": rows,
        "seed_aggregates": aggregates,
        "leaderboard": leaderboard,
        "best_validation_candidate": (leaderboard[0]["candidate_id"] if leaderboard else None),
        "promotion_status": "VALIDATION_ONLY_NOT_PROMOTED",
    }
