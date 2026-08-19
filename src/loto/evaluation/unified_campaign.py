"""Unified development-only evaluation across the broad model catalog and every game.

The campaign is deliberately fail-visible: every requested catalog x game combination
produces exactly one result row. Unsupported, unavailable and non-routable combinations are
retained instead of disappearing from a leaderboard.

Predictions are written and SHA-256 sealed before target actuals are read by the scoring
stage. Holdout and Prospective rows are never evaluated by this module.
"""

from __future__ import annotations

import hashlib
import os
import platform
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from loto.evaluation.metric_registry import REQUIRED_BASELINE_IDS, REQUIRED_POINT_METRICS
from loto.evaluation.metrics_general import positional_metrics
from loto.evaluation.path_codec import encode_path_component
from loto.evaluation.probabilistic_oof_adapter import (
    ProbabilisticScientificRoute,
    build_probabilistic_scientific_plan,
    predict_probabilistic_from_history,
)
from loto.evaluation.protocol_v2 import (
    BaselineManifest,
    EvaluationProtocolV2,
    GameGeometryIdentity,
    IdentityRef,
    MetricManifest,
    ResourceBudget,
    canonical_json_bytes,
    canonical_sha256,
    write_protocol_artifact,
)
from loto.evaluation.seed_summary import SeedMetricValue, summarize_seed_metric
from loto.evaluation.splits import rolling_folds, split_development_holdout
from loto.evaluation.theory_general import theoretical_bounds
from loto.game.geometry import GameGeometry, geometry_for, known_games
from loto.models.catalog import ModelSpec, get_model_spec
from loto.models.catalog_full import ModelEntry, build_catalog
from loto.models.factory import RuntimeModel
from loto.models.workers import PositionSeriesWorker
from loto.probabilistic.decoder import (
    DecodeObjective,
    decode_digit_distribution,
    decode_select_distribution,
)

CAMPAIGN_SCHEMA_VERSION = "1.0.0"
ADAPTER_IDENTITY = "unified-slot-candidate-and-position-worker-v1"
POST_PROCESSING_IDENTITY = "explicit-decoder-routing-v2"

Status = Literal[
    "SUCCEEDED",
    "PARTIAL_SEEDS",
    "FAILED",
    "UNAVAILABLE",
    "NOT_ROUTABLE",
    "UNSUPPORTED_GAME",
    "NON_STANDALONE_METHOD",
    "BASELINE_CONTROL",
]


class UnifiedCampaignConfig(BaseModel):
    """Result-affecting configuration for one all-model/all-game campaign."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_dir: Path
    git_commit: str
    games: tuple[str, ...] = tuple(known_games())
    model_ids: tuple[str, ...] | None = None
    seeds: tuple[int, ...] = (42, 1729, 20260730)
    folds: int = Field(default=5, ge=1)
    test_size: int = Field(default=20, ge=1)
    min_train_size: int = Field(default=100, ge=2)
    holdout_size: int = Field(default=50, ge=0)
    gap: int = Field(default=0, ge=0)
    tau: Literal[1] = 1
    feature_windows: tuple[int, ...] = (5, 10, 20)
    device: Literal["auto", "cpu", "cuda"] = "auto"
    precision: Literal["32", "16-mixed", "bf16-mixed"] = "32"
    max_trials: int = Field(default=10, ge=1)
    parallel_trials: int = Field(default=1, ge=1)
    wall_time_seconds: int = Field(default=1800, ge=1)
    max_steps: int = Field(default=50, ge=1)
    cpu_count: int = Field(default_factory=lambda: max(int(os.cpu_count() or 1), 1), ge=1)
    gpu_count: int = Field(default=0, ge=0)
    gpu_memory_bytes: int = Field(default=0, ge=0)
    code_hash: str | None = None

    @field_validator("games")
    @classmethod
    def validate_games(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        known = set(known_games())
        if not value or len(set(value)) != len(value):
            raise ValueError("games must be non-empty and unique")
        unknown = sorted(set(value).difference(known))
        if unknown:
            raise ValueError(f"unknown games: {unknown}")
        return value

    @field_validator("seeds")
    @classmethod
    def validate_seeds(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or len(set(value)) != len(value):
            raise ValueError("seeds must be non-empty and unique")
        if tuple(sorted(value)) != value:
            raise ValueError("seeds must be sorted for protocol identity")
        return value

    @field_validator("git_commit")
    @classmethod
    def validate_git_commit(cls, value: str) -> str:
        if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("git_commit must be a lowercase 40-character SHA")
        return value


@dataclass(frozen=True, slots=True)
class PreparedGame:
    geometry: GameGeometry
    development: pd.DataFrame
    holdout_rows: int
    folds: tuple[Any, ...]
    protocol: EvaluationProtocolV2


class _NotRoutable(RuntimeError):
    pass


class _UnsupportedGame(RuntimeError):
    pass


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resolved_code_hash(config: UnifiedCampaignConfig) -> str:
    if config.code_hash is not None:
        if len(config.code_hash) != 64 or any(
            ch not in "0123456789abcdef" for ch in config.code_hash
        ):
            raise ValueError("code_hash must be a lowercase 64-character SHA-256")
        return config.code_hash
    return _sha_text(f"{config.git_commit}:{ADAPTER_IDENTITY}:{POST_PROCESSING_IDENTITY}")


def _normalise_development(frame: pd.DataFrame, geometry: GameGeometry) -> pd.DataFrame:
    """Validate only the development slice and bind it to draw-step time."""

    data = frame.copy().reset_index(drop=True)
    columns = geometry.column_names()
    missing = [column for column in columns if column not in data.columns]
    if missing:
        raise ValueError(f"{geometry.key}: missing target columns: {missing}")
    if "draw_no" not in data.columns:
        data.insert(0, "draw_no", np.arange(1, len(data) + 1, dtype=int))
    draw_no = pd.to_numeric(data["draw_no"], errors="raise").astype(int)
    if draw_no.duplicated().any():
        raise ValueError(f"{geometry.key}: duplicate draw_no values")
    if not draw_no.is_monotonic_increasing:
        raise ValueError(f"{geometry.key}: draw_no must be strictly chronological")
    data["draw_no"] = draw_no

    # A common draw-step clock prevents calendar frequency differences from becoming a
    # hidden model advantage. Existing workers expecting dates receive one 7-day step per draw.
    data["draw_date"] = pd.Timestamp("2000-01-02") + pd.to_timedelta(
        np.arange(len(data), dtype=int) * 7, unit="D"
    )
    for column in columns:
        data[column] = pd.to_numeric(data[column], errors="raise")
        if not np.isfinite(data[column].to_numpy(dtype=float)).all():
            raise ValueError(f"{geometry.key}: non-finite target values in {column}")
    for row in data[columns].itertuples(index=False, name=None):
        geometry.validate_outcome(tuple(int(value) for value in row))
    return data


def _split_payload(folds: Sequence[Any], *, holdout_rows: int) -> dict[str, Any]:
    return {
        "holdout_rows": holdout_rows,
        "folds": [
            {
                "fold_id": fold.fold_id,
                "train_start": fold.train_start,
                "train_end": fold.train_end,
                "test_start": fold.test_start,
                "test_end": fold.test_end,
            }
            for fold in folds
        ],
    }


def _prepare_game(
    game: str,
    frame: pd.DataFrame,
    config: UnifiedCampaignConfig,
) -> PreparedGame:
    geometry = geometry_for(game)
    development_slice, holdout_slice = split_development_holdout(len(frame), config.holdout_size)
    development = _normalise_development(frame.iloc[development_slice], geometry)
    holdout_rows = int(holdout_slice.stop - holdout_slice.start)
    folds = tuple(
        rolling_folds(
            len(development),
            folds=config.folds,
            test_size=config.test_size,
            min_train_size=config.min_train_size,
            gap=config.gap,
            expanding=True,
        )
    )
    if not folds:
        raise ValueError(f"{game}: no chronological folds can be constructed")

    data_payload = development[["draw_no", *geometry.column_names()]].to_dict(orient="records")
    data_hash = canonical_sha256(data_payload)
    split_payload = _split_payload(folds, holdout_rows=holdout_rows)
    split_hash = canonical_sha256(split_payload)
    feature_payload = {
        "adapter": ADAPTER_IDENTITY,
        "windows": list(config.feature_windows),
        "time_axis": "DRAW_STEP_7D",
        "train_fit_only": True,
    }
    resource = ResourceBudget(
        cpu_count=config.cpu_count,
        gpu_count=config.gpu_count,
        gpu_memory_bytes=config.gpu_memory_bytes,
        wall_time_seconds=config.wall_time_seconds,
        max_trials=config.max_trials,
        parallel_trials=config.parallel_trials,
    )
    protocol = EvaluationProtocolV2(
        game_geometry=GameGeometryIdentity(
            game=geometry.key,
            family=geometry.family,
            positions=geometry.positions,
            universe_size=geometry.universe_size,
            value_min=geometry.value_min,
            value_max=geometry.value_max,
            ascending=geometry.ascending,
        ),
        data_snapshot=IdentityRef(identity=f"{game}-development-only", sha256=data_hash),
        split_manifest=IdentityRef(identity=f"{game}-rolling-folds", sha256=split_hash),
        feature_manifest=IdentityRef(
            identity=ADAPTER_IDENTITY,
            sha256=canonical_sha256(feature_payload),
        ),
        metric_manifest=MetricManifest(),
        baseline_manifest=BaselineManifest(),
        alpha=0.05,
        multiplicity_correction="holm",
        bootstrap_method="paired",
        bootstrap_repetitions=1000,
        conformal_method="none-development-campaign",
        conformal_alpha=0.1,
        sentinel_inventory=(
            "chronology",
            "duplicate_draw_no",
            "domain",
            "prediction_before_actual",
        ),
        sentinel_repetitions=1,
        post_processing_identity=IdentityRef(
            identity=POST_PROCESSING_IDENTITY,
            sha256=_sha_text(POST_PROCESSING_IDENTITY),
        ),
        reconciliation_identity=IdentityRef(identity="none", sha256=_sha_text("none")),
        seed_inventory=config.seeds,
        search_space_identity=IdentityRef(
            identity="bounded-common-budget",
            sha256=canonical_sha256(
                {
                    "max_trials": config.max_trials,
                    "parallel_trials": config.parallel_trials,
                    "max_steps": config.max_steps,
                }
            ),
        ),
        resource_budget=resource,
        package_versions={
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        code_hash=_resolved_code_hash(config),
        git_commit=config.git_commit,
    )
    return PreparedGame(geometry, development, holdout_rows, folds, protocol)


def _legalise(values: np.ndarray, geometry: GameGeometry) -> np.ndarray:
    row = np.clip(np.rint(np.asarray(values, dtype=float)), geometry.value_min, geometry.value_max)
    if not geometry.ascending:
        return row.astype(int)
    row = np.sort(row)
    for index in range(1, len(row)):
        if row[index] <= row[index - 1]:
            row[index] = row[index - 1] + 1
    overflow = int(max(row[-1] - geometry.value_max, 0))
    if overflow:
        row -= overflow
        for index in range(1, len(row)):
            if row[index] <= row[index - 1]:
                row[index] = row[index - 1] + 1
    row = np.clip(row, geometry.value_min, geometry.value_max)
    geometry.validate_outcome(tuple(int(value) for value in row))
    return row.astype(int)


def _mode(values: np.ndarray) -> float:
    unique, counts = np.unique(values, return_counts=True)
    return float(unique[np.argmax(counts)])


def _baseline_prediction(
    baseline_id: str,
    history: pd.DataFrame,
    geometry: GameGeometry,
    *,
    seed: int,
    target_index: int,
) -> np.ndarray:
    columns = geometry.column_names()
    values = history[columns].to_numpy(dtype=float)
    if not len(values):
        raise ValueError("baseline requires non-empty training history")
    if baseline_id == "random":
        rng = np.random.default_rng(seed * 1_000_003 + target_index)
        universe = np.arange(geometry.value_min, geometry.value_max + 1)
        if geometry.family == "select":
            pred = np.sort(rng.choice(universe, size=geometry.positions, replace=False))
        else:
            pred = rng.choice(universe, size=geometry.positions, replace=True)
    elif baseline_id == "fixed":
        pred = np.asarray(theoretical_bounds(geometry, tau=1).tau_prediction, dtype=float)
    elif baseline_id == "mean":
        pred = values.mean(axis=0)
    elif baseline_id == "median":
        pred = np.median(values, axis=0)
    elif baseline_id == "last":
        pred = values[-1]
    elif baseline_id == "frequency":
        pred = np.asarray([_mode(values[:, slot]) for slot in range(geometry.positions)])
    elif baseline_id == "statistical_ar1":
        result: list[float] = []
        for slot in range(geometry.positions):
            series = values[:, slot]
            if len(series) < 3 or float(np.var(series[:-1])) == 0.0:
                result.append(float(series[-1]))
                continue
            x = np.column_stack([np.ones(len(series) - 1), series[:-1]])
            coef, *_ = np.linalg.lstsq(x, series[1:], rcond=None)
            result.append(float(coef[0] + coef[1] * series[-1]))
        pred = np.asarray(result)
    else:  # registry and implementation must stay aligned
        raise KeyError(f"unknown baseline {baseline_id!r}")
    return _legalise(np.asarray(pred, dtype=float), geometry)


def _slot_candidate_rows(
    history: pd.DataFrame,
    geometry: GameGeometry,
    windows: tuple[int, ...],
    *,
    query_only: bool,
) -> pd.DataFrame:
    """Game-agnostic slot-conditioned candidate matrix with Train-only history."""

    columns = geometry.column_names()
    matrix = history[columns].to_numpy(dtype=int)
    candidate_values = np.arange(geometry.value_min, geometry.value_max + 1, dtype=int)
    target_indexes = [len(matrix)] if query_only else list(range(len(matrix)))
    rows: list[dict[str, Any]] = []
    for idx in target_indexes:
        for slot in range(geometry.positions):
            slot_history = matrix[:idx, slot]
            for candidate in candidate_values:
                row: dict[str, Any] = {
                    "draw_no": idx + 1,
                    "candidate_number": int(candidate),
                    "slot_index": slot + 1,
                    "slot_scaled": float((slot + 1) / geometry.positions),
                    "candidate_scaled": float(
                        (candidate - geometry.value_min) / max(geometry.universe_size - 1, 1)
                    ),
                    "selected": 0 if query_only else int(matrix[idx, slot] == candidate),
                }
                if len(slot_history):
                    row["freq_all"] = float(np.mean(slot_history == candidate))
                    matches = np.flatnonzero(slot_history == candidate)
                    row["gap_draws"] = (
                        float(idx - int(matches[-1])) if len(matches) else float(idx + 1)
                    )
                else:
                    row["freq_all"] = 0.0
                    row["gap_draws"] = float(idx + 1)
                for window in windows:
                    recent = slot_history[max(0, len(slot_history) - window) :]
                    row[f"freq_w{window}"] = (
                        float(np.mean(recent == candidate)) if len(recent) else 0.0
                    )
                rows.append(row)
    return pd.DataFrame(rows)


def _entry_to_spec(entry: ModelEntry) -> ModelSpec:
    try:
        return get_model_spec(entry.model_id)
    except KeyError:
        return ModelSpec(
            model_id=entry.model_id,
            family=entry.family,
            library=entry.library,
            task="position_series" if entry.task == "position" else entry.task,
            class_name=entry.class_name,
            priority=entry.priority,
            package=entry.package,
            capabilities=entry.capabilities,
            default_params=dict(entry.default_params),
            notes=entry.notes,
        )


def _candidate_model_supported(spec: ModelSpec) -> bool:
    return spec.library in {"sklearn", "lightgbm", "xgboost", "catboost"}


def _decode_candidate_probability_matrix(
    matrix: np.ndarray,
    geometry: GameGeometry,
    *,
    tau: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Decode the slot-conditioned binary candidate surface without inventing worker PMFs."""
    adapter_id = "row-normalized-slot-binary-probability-v1"
    if geometry.family == "select":
        values = decode_select_distribution(
            matrix,
            geometry,
            objective=DecodeObjective.WITHIN_TAU,
            tau=tau,
        )
        decoder_id = "within-tau-constrained-dp-v1"
    else:
        values = decode_digit_distribution(
            matrix,
            geometry,
            objective=DecodeObjective.WITHIN_TAU,
            tau=tau,
        )
        decoder_id = "within-tau-independent-slot-v1"
    return np.asarray(values, dtype=int), {
        "distribution_source": "slot_binary_candidate_probabilities",
        "distribution_adapter_id": adapter_id,
        "decoder_id": decoder_id,
        "decoder_objective": DecodeObjective.WITHIN_TAU.value,
        "tau": tau,
    }


def _model_prediction(
    entry: ModelEntry,
    history: pd.DataFrame,
    geometry: GameGeometry,
    config: UnifiedCampaignConfig,
    *,
    seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    if entry.task == "reconciliation":
        raise _NotRoutable("reconciliation methods are not standalone forecasters")
    if entry.model_id in {"uniform", "frequency", "position-median", "position-modal"}:
        raise _NotRoutable("catalog control is represented by the mandatory baseline suite")

    spec = _entry_to_spec(entry)
    if not spec.available:
        raise ModuleNotFoundError(f"optional package unavailable: {spec.package}")

    if entry.task == "candidate":
        if not _candidate_model_supported(spec):
            raise _NotRoutable(
                "candidate estimator has no unified point-forecast bridge: "
                f"{spec.library}/{spec.class_name}"
            )
        train = _slot_candidate_rows(history, geometry, config.feature_windows, query_only=False)
        query = _slot_candidate_rows(history, geometry, config.feature_windows, query_only=True)
        runtime = RuntimeModel(spec, seed=seed).fit_candidate(train)
        result = runtime.predict_candidate(query)
        probabilities = np.asarray(result.candidate_probabilities, dtype=float)
        expected = geometry.positions * geometry.universe_size
        if probabilities.shape != (expected,) or not np.isfinite(probabilities).all():
            raise ValueError(
                f"candidate probabilities must have shape ({expected},), got {probabilities.shape}"
            )
        matrix = probabilities.reshape(geometry.positions, geometry.universe_size)
        pred, decoder_metadata = _decode_candidate_probability_matrix(
            matrix,
            geometry,
            tau=config.tau,
        )
        return pred, {
            "route": "slot_conditioned_candidate",
            "library": spec.library,
            "class_name": spec.class_name,
            **decoder_metadata,
        }

    if entry.task not in {"position", "position_series", "foundation"}:
        raise _NotRoutable(f"unsupported task for unified campaign: {entry.task}")

    worker_libraries = {
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
    if spec.library not in worker_libraries:
        raise _NotRoutable(f"no PositionSeriesWorker route for library={spec.library}")
    if spec.class_name == "AutoHINT" and geometry.positions != 7:
        raise _UnsupportedGame("AutoHINT currently requires exactly seven coherent series")

    params = dict(spec.default_params)
    if spec.library == "neuralforecast":
        params.setdefault("max_steps", config.max_steps)
        if spec.class_name in {"TSMixer", "TimeMixer", "iTransformer"}:
            params["n_series"] = geometry.positions
    elif spec.library == "neuralforecast_auto":
        params.setdefault("num_samples", config.max_trials)
        params.setdefault("parallel_trials", config.parallel_trials)
        params.setdefault("cpus", 1)
        params.setdefault("gpus", 1 if config.device == "cuda" else 0)

    output = PositionSeriesWorker(
        spec,
        params,
        seed=seed,
        device=config.device,
        precision=config.precision,
        position_columns=geometry.column_names(),
    ).forecast(history)
    values = np.asarray(output.position_values, dtype=float)
    if values.shape != (geometry.positions,) or not np.isfinite(values).all():
        raise ValueError(
            f"worker output must have shape ({geometry.positions},), got {values.shape}"
        )
    return _legalise(values, geometry), {
        "route": "position_series_worker",
        "library": spec.library,
        "class_name": spec.class_name,
        "distribution_source": "none",
        "distribution_adapter_id": "none",
        "decoder_id": "point-legalise-v1",
        "decoder_objective": "point",
        "worker": output.metadata,
    }


def _canonical_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
    geometry: GameGeometry,
    *,
    tau: int,
) -> dict[str, Any]:
    raw = positional_metrics(actual, predicted, geometry, tau=tau)
    by_position = {
        str(position): float(raw[f"position_{position}_within_{tau}"])
        for position in range(1, geometry.positions + 1)
    }
    return {
        "hit_at_1": float(raw[f"element_within_{tau}"]),
        "position_hit_at_1": float(np.mean(list(by_position.values()))),
        "position_hit_at_1_by_position": by_position,
        "all_positions_hit_at_1": float(raw[f"row_within_{tau}"]),
        "mae": float(raw["position_mae"]),
        "mse": float(raw["position_mse"]),
        "rmse": float(raw["position_rmse"]),
    }


def _write_prediction_lock(
    path: Path,
    *,
    protocol_hash: str,
    game: str,
    candidate_id: str,
    seed: int,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    sealed_at = datetime.now(UTC).isoformat()
    payload = {
        "schema_version": "prediction-lock-v1",
        "protocol_hash": protocol_hash,
        "game": game,
        "candidate_id": candidate_id,
        "seed": seed,
        "actuals_known": False,
        "sealed_at_utc": sealed_at,
        "predictions": records,
    }
    data = canonical_json_bytes(payload) + b"\n"
    digest = hashlib.sha256(data).hexdigest()
    if path.exists():
        raise FileExistsError(f"refusing to overwrite prediction lock: {path}")
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return {"path": str(path), "sha256": digest, "sealed_at_utc": sealed_at, "bytes": len(data)}


def _evaluate_seed(
    prepared: PreparedGame,
    candidate_id: str,
    seed: int,
    config: UnifiedCampaignConfig,
    *,
    baseline_id: str | None = None,
    entry: ModelEntry | None = None,
    probabilistic_route: ProbabilisticScientificRoute | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    runtime_samples: list[dict[str, Any]] = []
    for fold in prepared.folds:
        for draw_index in range(fold.test_start, fold.test_end):
            history = prepared.development.iloc[:draw_index].copy()
            started = time.perf_counter()
            if baseline_id is not None:
                pred = _baseline_prediction(
                    baseline_id,
                    history,
                    prepared.geometry,
                    seed=seed,
                    target_index=draw_index,
                )
                metadata: dict[str, Any] = {
                    "route": "mandatory_baseline",
                    "baseline": baseline_id,
                    "distribution_source": "baseline_native",
                    "distribution_adapter_id": "none",
                    "decoder_id": f"baseline-{baseline_id}-v1",
                    "decoder_objective": "baseline_native",
                }
            elif probabilistic_route is not None:
                prediction = predict_probabilistic_from_history(
                    history,
                    probabilistic_route,
                    seed=seed,
                    protocol_hash=prepared.protocol.protocol_hash,
                    device=config.device,
                )
                pred = np.asarray(prediction.values, dtype=int)
                metadata = dict(prediction.metadata)
            else:
                if entry is None:
                    raise AssertionError("model entry is required")
                pred, metadata = _model_prediction(
                    entry,
                    history,
                    prepared.geometry,
                    config,
                    seed=seed,
                )
            records.append(
                {
                    "fold_id": fold.fold_id,
                    "draw_index": draw_index,
                    "draw_no": int(prepared.development.iloc[draw_index]["draw_no"]),
                    "prediction": [int(value) for value in pred],
                }
            )
            runtime_samples.append(
                {
                    "fold_id": fold.fold_id,
                    "draw_index": draw_index,
                    "elapsed_seconds": time.perf_counter() - started,
                    "metadata": metadata,
                }
            )

    safe_id = encode_path_component(candidate_id)
    lock = _write_prediction_lock(
        config.output_dir
        / "prediction_locks"
        / prepared.geometry.key
        / safe_id
        / f"seed-{seed}.json",
        protocol_hash=prepared.protocol.protocol_hash,
        game=prepared.geometry.key,
        candidate_id=candidate_id,
        seed=seed,
        records=records,
    )

    # Target actuals are read only after the durable prediction lock exists.
    actual = np.asarray(
        [
            prepared.development.iloc[item["draw_index"]][
                prepared.geometry.column_names()
            ].to_numpy(dtype=float)
            for item in records
        ]
    )
    predicted = np.asarray([item["prediction"] for item in records], dtype=float)
    return {
        "seed": seed,
        "metrics": _canonical_metrics(actual, predicted, prepared.geometry, tau=config.tau),
        "prediction_lock": lock,
        "runtime_samples": runtime_samples,
    }


def _seed_summaries(seed_results: list[dict[str, Any]], seeds: tuple[int, ...]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for metric_id in REQUIRED_POINT_METRICS:
        values = [
            SeedMetricValue(seed=int(item["seed"]), value=float(item["metrics"][metric_id]))
            for item in seed_results
        ]
        output[metric_id] = summarize_seed_metric(
            metric_id,
            values,
            expected_seeds=seeds,
        ).to_dict()
    return output


def _result_from_failure(
    *,
    game: str,
    candidate_id: str,
    source: str,
    status: Status,
    reason: str,
    library: str,
    task: str,
    protocol_hash: str,
) -> dict[str, Any]:
    return {
        "game": game,
        "candidate_id": candidate_id,
        "source": source,
        "library": library,
        "task": task,
        "status": status,
        "reason": reason,
        "protocol_hash": protocol_hash,
        "seed_results": [],
        "seed_summary": {},
    }


def _evaluate_candidate(
    prepared: PreparedGame,
    config: UnifiedCampaignConfig,
    *,
    candidate_id: str,
    source: str,
    library: str,
    task: str,
    baseline_id: str | None = None,
    entry: ModelEntry | None = None,
    probabilistic_route: ProbabilisticScientificRoute | None = None,
) -> dict[str, Any]:
    if probabilistic_route is not None and not probabilistic_route.allowed:
        unavailable_reasons = {"BACKEND_UNAVAILABLE", "MODEL_BLOCKED"}
        unsupported_reasons = {"TARGET_MODE_UNSUPPORTED", "DRAW_ORDER_REQUIRED"}
        if probabilistic_route.reason_code in unavailable_reasons:
            status: Status = "UNAVAILABLE"
        elif probabilistic_route.reason_code in unsupported_reasons:
            status = "UNSUPPORTED_GAME"
        else:
            status = "NOT_ROUTABLE"
        return _result_from_failure(
            game=prepared.geometry.key,
            candidate_id=candidate_id,
            source=source,
            status=status,
            reason=f"{probabilistic_route.reason_code}: {probabilistic_route.details}",
            library=library,
            task=task,
            protocol_hash=prepared.protocol.protocol_hash,
        )
    seed_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for seed in config.seeds:
        try:
            seed_results.append(
                _evaluate_seed(
                    prepared,
                    candidate_id,
                    seed,
                    config,
                    baseline_id=baseline_id,
                    entry=entry,
                    probabilistic_route=probabilistic_route,
                )
            )
        except _UnsupportedGame as exc:
            return _result_from_failure(
                game=prepared.geometry.key,
                candidate_id=candidate_id,
                source=source,
                status="UNSUPPORTED_GAME",
                reason=str(exc),
                library=library,
                task=task,
                protocol_hash=prepared.protocol.protocol_hash,
            )
        except _NotRoutable as exc:
            status: Status = "NON_STANDALONE_METHOD" if task == "reconciliation" else "NOT_ROUTABLE"
            return _result_from_failure(
                game=prepared.geometry.key,
                candidate_id=candidate_id,
                source=source,
                status=status,
                reason=str(exc),
                library=library,
                task=task,
                protocol_hash=prepared.protocol.protocol_hash,
            )
        except ModuleNotFoundError as exc:
            return _result_from_failure(
                game=prepared.geometry.key,
                candidate_id=candidate_id,
                source=source,
                status="UNAVAILABLE",
                reason=str(exc),
                library=library,
                task=task,
                protocol_hash=prepared.protocol.protocol_hash,
            )
        except Exception as exc:  # noqa: BLE001 - fail-visible campaign rows
            failures.append({"seed": seed, "type": type(exc).__name__, "reason": str(exc)})
    if len(seed_results) != len(config.seeds):
        return {
            "game": prepared.geometry.key,
            "candidate_id": candidate_id,
            "source": source,
            "library": library,
            "task": task,
            "status": "PARTIAL_SEEDS" if seed_results else "FAILED",
            "reason": "one or more approved seeds failed",
            "failures": failures,
            "protocol_hash": prepared.protocol.protocol_hash,
            "seed_results": seed_results,
            "seed_summary": {},
        }
    return {
        "game": prepared.geometry.key,
        "candidate_id": candidate_id,
        "source": source,
        "library": library,
        "task": task,
        "status": "SUCCEEDED",
        "reason": "",
        "failures": failures,
        "protocol_hash": prepared.protocol.protocol_hash,
        "seed_results": seed_results,
        "seed_summary": _seed_summaries(seed_results, config.seeds),
    }


def _selected_entries(config: UnifiedCampaignConfig) -> list[ModelEntry]:
    entries = build_catalog()
    if config.model_ids is None:
        return entries
    wanted = set(config.model_ids)
    return [entry for entry in entries if entry.model_id in wanted]


def _selected_probabilistic_routes(
    config: UnifiedCampaignConfig,
) -> list[ProbabilisticScientificRoute]:
    routes = list(build_probabilistic_scientific_plan(config.games))
    if config.model_ids is None:
        return routes
    wanted = set(config.model_ids)
    return [route for route in routes if route.model_id in wanted]


def build_campaign_plan(config: UnifiedCampaignConfig) -> list[dict[str, str]]:
    """Return the complete requested unified 250-identity x game matrix."""

    entries = _selected_entries(config)
    probabilistic_routes = _selected_probabilistic_routes(config)
    broad_ids = {entry.model_id for entry in entries}
    probabilistic_ids = {route.model_id for route in probabilistic_routes}
    collisions = sorted(broad_ids.intersection(probabilistic_ids))
    if collisions:
        raise AssertionError(f"unified scientific identity collision: {collisions}")
    if config.model_ids is not None:
        wanted = set(config.model_ids)
        missing = sorted(wanted.difference(broad_ids | probabilistic_ids))
        if missing:
            raise KeyError(f"unknown model IDs: {missing}")

    broad_rows = [
        {
            "game": game,
            "candidate_id": entry.model_id,
            "library": entry.library,
            "task": entry.task,
        }
        for game in config.games
        for entry in entries
    ]
    probabilistic_rows = [
        {
            "game": route.game,
            "candidate_id": route.model_id,
            "library": "probabilistic",
            "task": route.target_mode or "probabilistic",
        }
        for route in probabilistic_routes
    ]
    rows = broad_rows + probabilistic_rows
    pair_keys = {(row["game"], row["candidate_id"]) for row in rows}
    if len(pair_keys) != len(rows):
        raise AssertionError("unified campaign plan contains duplicate model/game pairs")
    return rows


def _leaderboards(
    results: list[dict[str, Any]], games: tuple[str, ...]
) -> dict[str, list[dict[str, Any]]]:
    boards: dict[str, list[dict[str, Any]]] = {}
    for game in games:
        rows = [row for row in results if row["game"] == game and row["status"] == "SUCCEEDED"]
        rows.sort(
            key=lambda row: (
                -float(row["seed_summary"]["hit_at_1"]["mean"]),
                -float(row["seed_summary"]["all_positions_hit_at_1"]["mean"]),
                float(row["seed_summary"]["mae"]["mean"]),
                row["candidate_id"],
            )
        )
        boards[game] = [
            {
                "rank": index + 1,
                "candidate_id": row["candidate_id"],
                "source": row["source"],
                "library": row["library"],
                "hit_at_1": row["seed_summary"]["hit_at_1"]["mean"],
                "all_positions_hit_at_1": row["seed_summary"]["all_positions_hit_at_1"]["mean"],
                "mae": row["seed_summary"]["mae"]["mean"],
                "rmse": row["seed_summary"]["rmse"]["mean"],
            }
            for index, row in enumerate(rows)
        ]
    return boards


def _macro_summary(results: list[dict[str, Any]], games: tuple[str, ...]) -> list[dict[str, Any]]:
    by_candidate: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        if row["source"] not in {"catalog", "probabilistic"}:
            continue
        by_candidate.setdefault(row["candidate_id"], []).append(row)
    summary: list[dict[str, Any]] = []
    for candidate_id, rows in by_candidate.items():
        succeeded = [row for row in rows if row["status"] == "SUCCEEDED"]
        complete = len(succeeded) == len(games)
        summary.append(
            {
                "candidate_id": candidate_id,
                "games_requested": len(games),
                "games_succeeded": len(succeeded),
                "all_games_complete": complete,
                "macro_hit_at_1": float(
                    np.mean([row["seed_summary"]["hit_at_1"]["mean"] for row in succeeded])
                )
                if complete
                else None,
                "macro_mae": float(
                    np.mean([row["seed_summary"]["mae"]["mean"] for row in succeeded])
                )
                if complete
                else None,
                "statuses": {row["game"]: row["status"] for row in rows},
            }
        )
    summary.sort(
        key=lambda row: (
            not row["all_games_complete"],
            -(row["macro_hit_at_1"] or -1.0),
            row["candidate_id"],
        )
    )
    return summary


def run_unified_campaign(
    frames: Mapping[str, pd.DataFrame],
    config: UnifiedCampaignConfig,
) -> dict[str, Any]:
    """Execute the complete requested model x game campaign and write immutable evidence."""

    output = config.output_dir
    if output.exists():
        raise FileExistsError(f"refusing to reuse campaign output directory: {output}")
    output.mkdir(parents=True)
    entries = _selected_entries(config)
    probabilistic_routes = _selected_probabilistic_routes(config)
    probabilistic_ids = {route.model_id for route in probabilistic_routes}
    plan = build_campaign_plan(config)
    unified_models = len(entries) + len(probabilistic_ids)
    expected_pairs = unified_models * len(config.games)
    if len(plan) != expected_pairs:
        raise AssertionError("campaign plan does not cover every requested model/game pair")

    prepared: dict[str, PreparedGame] = {}
    for game in config.games:
        if game not in frames:
            raise KeyError(f"missing input frame for game={game}")
        prepared[game] = _prepare_game(game, frames[game], config)
        write_protocol_artifact(output / "protocols" / f"{game}.json", prepared[game].protocol)

    results: list[dict[str, Any]] = []
    for game in config.games:
        context = prepared[game]
        for baseline_id in REQUIRED_BASELINE_IDS:
            results.append(
                _evaluate_candidate(
                    context,
                    config,
                    candidate_id=f"baseline:{baseline_id}",
                    source="baseline",
                    library="baseline",
                    task="position",
                    baseline_id=baseline_id,
                )
            )
        for entry in entries:
            results.append(
                _evaluate_candidate(
                    context,
                    config,
                    candidate_id=entry.model_id,
                    source="catalog",
                    library=entry.library,
                    task=entry.task,
                    entry=entry,
                )
            )
        for route in probabilistic_routes:
            if route.game != game:
                continue
            results.append(
                _evaluate_candidate(
                    context,
                    config,
                    candidate_id=route.model_id,
                    source="probabilistic",
                    library="probabilistic",
                    task=route.target_mode or "probabilistic",
                    probabilistic_route=route,
                )
            )

    catalog_results = [row for row in results if row["source"] in {"catalog", "probabilistic"}]
    if len(catalog_results) != expected_pairs:
        raise AssertionError("result matrix lost one or more model/game combinations")
    pair_keys = {(row["game"], row["candidate_id"]) for row in catalog_results}
    if len(pair_keys) != expected_pairs:
        raise AssertionError("result matrix contains duplicate or missing model/game pairs")

    leaderboards = _leaderboards(results, config.games)
    macro = _macro_summary(results, config.games)
    status_counts: dict[str, int] = {}
    for row in catalog_results:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    summary = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "status": "SUCCEEDED" if status_counts.get("SUCCEEDED", 0) == expected_pairs else "PARTIAL",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "git_commit": config.git_commit,
        "code_hash": _resolved_code_hash(config),
        "games": list(config.games),
        "catalog_models": unified_models,
        "broad_catalog_models": len(entries),
        "probabilistic_catalog_models": len(probabilistic_ids),
        "expected_model_game_pairs": expected_pairs,
        "observed_model_game_pairs": len(catalog_results),
        "matrix_complete": len(catalog_results) == expected_pairs
        and len(pair_keys) == expected_pairs,
        "status_counts": status_counts,
        "primary_metric": "hit_at_1",
        "required_metrics": list(REQUIRED_POINT_METRICS),
        "required_baselines": list(REQUIRED_BASELINE_IDS),
        "seeds": list(config.seeds),
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
        "results": results,
        "leaderboards": leaderboards,
        "macro_summary": macro,
    }
    (output / "campaign_summary.json").write_bytes(canonical_json_bytes(summary) + b"\n")

    flat_rows: list[dict[str, Any]] = []
    for row in results:
        flat = {
            "game": row["game"],
            "candidate_id": row["candidate_id"],
            "source": row["source"],
            "library": row["library"],
            "task": row["task"],
            "status": row["status"],
            "reason": row.get("reason", ""),
            "protocol_hash": row["protocol_hash"],
        }
        for metric_id in REQUIRED_POINT_METRICS:
            summary_item = row.get("seed_summary", {}).get(metric_id)
            flat[f"{metric_id}_mean"] = summary_item["mean"] if summary_item else None
            flat[f"{metric_id}_variance"] = (
                summary_item["population_variance"] if summary_item else None
            )
            flat[f"{metric_id}_worst"] = summary_item["worst_value"] if summary_item else None
            flat[f"{metric_id}_worst_seed"] = summary_item["worst_seed"] if summary_item else None
        flat_rows.append(flat)
    pd.DataFrame(flat_rows).to_csv(output / "model_game_results.csv", index=False)
    pd.DataFrame(macro).to_csv(output / "all_game_macro_summary.csv", index=False)

    artifact_paths = sorted(
        path for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    checksum_lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}"
        for path in artifact_paths
    ]
    (output / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return summary
