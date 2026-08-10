"""Leakage-safe OOF target orchestration for Timer Base 84M."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from loto.adapters.timer_base_84m.contracts import (
    ArtifactPaths,
    ChronologyEvidence,
    TimerRequest,
    TimerResponse,
)
from loto.evaluation.metric_registry import (
    REQUIRED_POINT_METRICS,
)
from loto.evaluation.metrics_general import (
    positional_metrics,
)
from loto.evaluation.prediction_seal import (
    SealedPrediction,
    seal_prediction_record,
    sha256_file,
    utc_now,
    verify_sealed_prediction,
    write_json_once,
)
from loto.evaluation.raw_baselines import (
    RawBaselinePrediction,
    geometry_for_logical_game,
    predict_raw_baselines,
)
from loto.timer_base_84m_campaign.chronology import (
    TimeAxis,
    validate_chronology,
)
from loto.timer_base_84m_campaign.geometry import (
    Game,
    geometry_for as timer_geometry_for,
)
from loto.timer_base_84m_campaign.provenance import (
    CONFIG_SHA256,
    LICENSE,
    MODEL_ID,
    MODEL_REVISION,
    OBSERVED_SOURCE_HEAD,
    REPO_ID,
    SOURCE_REVISION,
    TRANSFORMERS_VERSION,
    WEIGHT_SHA256,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")

TimerPredictor = Callable[
    [TimerRequest],
    TimerResponse,
]


@dataclass(frozen=True, slots=True)
class ActualReveal:
    game_id: str
    target_draw_no: int
    target_ds: date
    values: tuple[float, ...]
    actual_read_at_utc: str


@dataclass(frozen=True, slots=True)
class TimerPredictionSpec:
    candidate_id: str
    target_layout: Literal[
        "position_univariate",
        "position_panel_batched_univariate",
    ]
    seed: int
    requested_device: Literal[
        "cpu",
        "cuda",
    ] = "cuda"


@dataclass(frozen=True, slots=True)
class TargetBundleResult:
    score_path: Path
    score_sha256: str
    seals: tuple[SealedPrediction, ...]
    actual_reveal: ActualReveal


def _position_columns(
    game_id: str,
) -> tuple[str, ...]:
    geometry = timer_geometry_for(
        Game(game_id)
    )

    return tuple(
        f"N{index}"
        for index in range(
            1,
            geometry.position_count + 1,
        )
    )


class DevelopmentSnapshotReader:
    """Read pre-target context first and target actual only after seals."""

    def __init__(
        self,
        snapshot_root: Path,
    ) -> None:
        self.snapshot_root = (
            snapshot_root.expanduser().resolve()
        )

    def _path(
        self,
        game_id: str,
    ) -> Path:
        path = (
            self.snapshot_root
            / f"{game_id}.parquet"
        )

        if not path.is_file():
            raise FileNotFoundError(path)

        return path

    def read_context(
        self,
        *,
        game_id: str,
        target_draw_no: int,
        context_length: int,
    ) -> pd.DataFrame:
        first_draw = (
            target_draw_no
            - context_length
        )

        if first_draw < 1:
            raise ValueError(
                "context extends before draw 1"
            )

        columns = (
            "game_id",
            "draw_no",
            "ds",
            *_position_columns(game_id),
        )

        frame = pd.read_parquet(
            self._path(game_id),
            columns=list(columns),
            filters=[
                (
                    "draw_no",
                    ">=",
                    first_draw,
                ),
                (
                    "draw_no",
                    "<",
                    target_draw_no,
                ),
            ],
            engine="pyarrow",
        ).sort_values(
            "draw_no",
            kind="stable",
        )

        expected_draws = list(
            range(
                first_draw,
                target_draw_no,
            )
        )

        actual_draws = (
            frame["draw_no"]
            .astype(int)
            .tolist()
        )

        if actual_draws != expected_draws:
            raise ValueError(
                "context draw identities are "
                "missing, duplicated, or unordered"
            )

        if len(frame) != context_length:
            raise ValueError(
                "context length mismatch"
            )

        if set(
            frame["game_id"].astype(str)
        ) != {game_id}:
            raise ValueError(
                "context game identity mismatch"
            )

        dates = pd.to_datetime(
            frame["ds"],
            errors="raise",
        )

        if (
            not dates.is_monotonic_increasing
            or dates.duplicated().any()
        ):
            raise ValueError(
                "context dates must be unique "
                "and strictly increasing"
            )

        values = frame.loc[
            :,
            list(
                _position_columns(game_id)
            ),
        ].to_numpy(dtype=float)

        if not np.isfinite(values).all():
            raise ValueError(
                "context contains non-finite values"
            )

        return frame.reset_index(
            drop=True
        )

    def read_actual(
        self,
        *,
        game_id: str,
        target_draw_no: int,
        expected_target_ds: date,
        seals: Sequence[SealedPrediction],
    ) -> ActualReveal:
        if not seals:
            raise ValueError(
                "actual reveal requires at least "
                "one prediction seal"
            )

        for sealed in seals:
            verify_sealed_prediction(
                sealed
            )

        columns = (
            "game_id",
            "draw_no",
            "ds",
            *_position_columns(game_id),
        )

        frame = pd.read_parquet(
            self._path(game_id),
            columns=list(columns),
            filters=[
                (
                    "draw_no",
                    "==",
                    target_draw_no,
                )
            ],
            engine="pyarrow",
        )

        if len(frame) != 1:
            raise ValueError(
                "target actual identity is not unique"
            )

        row = frame.iloc[0]

        if str(row["game_id"]) != game_id:
            raise ValueError(
                "target actual game mismatch"
            )

        if int(row["draw_no"]) != target_draw_no:
            raise ValueError(
                "target draw identity mismatch"
            )

        target_ds = pd.Timestamp(
            row["ds"]
        ).date()

        if target_ds != expected_target_ds:
            raise ValueError(
                "target date identity mismatch"
            )

        values = tuple(
            float(row[column])
            for column in _position_columns(
                game_id
            )
        )

        if not np.isfinite(
            np.asarray(values, dtype=float)
        ).all():
            raise ValueError(
                "target actual contains "
                "non-finite values"
            )

        return ActualReveal(
            game_id=game_id,
            target_draw_no=target_draw_no,
            target_ds=target_ds,
            values=values,
            actual_read_at_utc=utc_now(),
        )


def canonical_point_metrics(
    *,
    game_id: str,
    actual: Sequence[float],
    predicted: Sequence[float],
) -> tuple[
    dict[str, float],
    dict[str, float],
]:
    geometry = geometry_for_logical_game(
        game_id
    )

    actual_matrix = np.asarray(
        actual,
        dtype=float,
    ).reshape(
        1,
        geometry.positions,
    )

    predicted_matrix = np.asarray(
        predicted,
        dtype=float,
    ).reshape(
        1,
        geometry.positions,
    )

    raw = positional_metrics(
        actual_matrix,
        predicted_matrix,
        geometry,
        tau=1,
    )

    metrics = {
        "hit_at_1":
            float(raw["element_within_1"]),
        "position_hit_at_1":
            float(
                np.mean(
                    [
                        raw[
                            f"position_{index}_within_1"
                        ]
                        for index in range(
                            1,
                            geometry.positions + 1,
                        )
                    ]
                )
            ),
        "all_positions_hit_at_1":
            float(raw["row_within_1"]),
        "mae":
            float(raw["position_mae"]),
        "mse":
            float(raw["position_mse"]),
        "rmse":
            float(raw["position_rmse"]),
    }

    if tuple(metrics) != REQUIRED_POINT_METRICS:
        raise RuntimeError(
            "canonical metric inventory mismatch"
        )

    by_position = {
        f"N{index}":
            float(
                raw[
                    f"position_{index}_within_1"
                ]
            )
        for index in range(
            1,
            geometry.positions + 1,
        )
    }

    return metrics, by_position


def build_timer_request(
    *,
    context: pd.DataFrame,
    game_id: str,
    spec: TimerPredictionSpec,
    request_run_id: str,
    artifact_paths: ArtifactPaths,
) -> TimerRequest:
    if _SAFE_ID.fullmatch(
        request_run_id
    ) is None:
        raise ValueError(
            f"unsafe run id: {request_run_id!r}"
        )

    timer_game = Game(game_id)
    columns = _position_columns(game_id)

    draw_numbers = tuple(
        int(value)
        for value in context[
            "draw_no"
        ].tolist()
    )

    dates = tuple(
        pd.Timestamp(value).date()
        for value in context[
            "ds"
        ].tolist()
    )

    mapping_sha = validate_chronology(
        game=timer_game,
        time_axis=TimeAxis.DRAW_SEQUENCE,
        draw_numbers=draw_numbers,
        dates=dates,
        cutoff_draw_no=draw_numbers[-1],
        cutoff_date=dates[-1],
        actuals_used=False,
    )

    chronology = ChronologyEvidence(
        time_axis=TimeAxis.DRAW_SEQUENCE,
        cutoff_draw_no=draw_numbers[-1],
        cutoff_date=dates[-1],
        draw_numbers=draw_numbers,
        dates=dates,
        mapping_sha256=mapping_sha,
        future_actuals_present=False,
        duplicate_free=True,
        strictly_increasing=True,
        gap_free=True,
    )

    series = tuple(
        tuple(
            float(value)
            for value in context[
                column
            ].tolist()
        )
        for column in columns
    )

    payload = {
        "schema_version":
            "timer-base-84m.request.v1",
        "run_id":
            request_run_id,
        "operation":
            "predict",
        "model_id":
            MODEL_ID,
        "repo_id":
            REPO_ID,
        "package_version":
            TRANSFORMERS_VERSION,
        "source_revision":
            SOURCE_REVISION,
        "observed_source_head":
            OBSERVED_SOURCE_HEAD,
        "model_revision":
            MODEL_REVISION,
        "config_sha256":
            CONFIG_SHA256,
        "weight_sha256":
            WEIGHT_SHA256,
        "license":
            LICENSE,
        "game":
            timer_game,
        "target_layout":
            spec.target_layout,
        "context_length":
            len(context),
        "prediction_length":
            1,
        "seed":
            spec.seed,
        "requested_device":
            spec.requested_device,
        "input_shape":
            (
                len(columns),
                len(context),
            ),
        "series":
            series,
        "past_covariates":
            None,
        "known_future_covariates":
            None,
        "chronology_evidence":
            chronology,
        "actuals_used":
            False,
        "artifact_paths":
            artifact_paths,
    }

    return TimerRequest.model_validate(
        payload
    )


def _score_payload(
    *,
    game_id: str,
    target_draw_no: int,
    target_ds: date,
    actual: ActualReveal,
    sealed: SealedPrediction,
    prediction_id: str,
    predicted: Sequence[float],
) -> dict[str, object]:
    metrics, by_position = (
        canonical_point_metrics(
            game_id=game_id,
            actual=actual.values,
            predicted=predicted,
        )
    )

    if (
        actual.actual_read_at_utc
        < sealed.sealed_at_utc
    ):
        raise RuntimeError(
            "actual read timestamp precedes "
            "prediction seal timestamp"
        )

    return {
        "prediction_id":
            prediction_id,
        "game_id":
            game_id,
        "target_draw_no":
            target_draw_no,
        "target_ds":
            target_ds.isoformat(),
        "prediction_record_sha256":
            sealed.record_sha256,
        "prediction_sealed_at_utc":
            sealed.sealed_at_utc,
        "actual_read_at_utc":
            actual.actual_read_at_utc,
        "target_actual":
            list(actual.values),
        "prediction":
            [
                float(value)
                for value in predicted
            ],
        "metrics":
            metrics,
        "position_hit_at_1":
            by_position,
    }


def run_baseline_target_bundle(
    *,
    reader: DevelopmentSnapshotReader,
    output_dir: Path,
    run_id: str,
    game_id: str,
    target_draw_no: int,
    target_ds: date,
    context_length: int,
    seeds: tuple[int, ...],
) -> TargetBundleResult:
    """Seal all baseline predictions before revealing one target actual."""

    if output_dir.exists():
        raise FileExistsError(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    context = reader.read_context(
        game_id=game_id,
        target_draw_no=target_draw_no,
        context_length=context_length,
    )

    columns = _position_columns(game_id)

    history = context.loc[
        :,
        list(columns),
    ].to_numpy(dtype=float)

    predictions = predict_raw_baselines(
        history,
        game_id=game_id,
        target_draw_no=target_draw_no,
        seeds=seeds,
    )

    sealed_pairs: list[
        tuple[
            RawBaselinePrediction,
            SealedPrediction,
        ]
    ] = []

    for prediction in predictions:
        record = {
            "schema_version":
                "oof-baseline-prediction.v1",
            "run_id":
                run_id,
            "prediction_id":
                prediction.prediction_id,
            "candidate_type":
                "baseline",
            "baseline_id":
                prediction.baseline_id,
            "seed":
                prediction.seed,
            "game_id":
                game_id,
            "target_draw_no":
                target_draw_no,
            "target_ds_identity":
                target_ds.isoformat(),
            "context_first_draw_no":
                int(context.iloc[0]["draw_no"]),
            "context_last_draw_no":
                int(context.iloc[-1]["draw_no"]),
            "prediction":
                list(prediction.values),
            "post_processing":
                "raw_point_no_transform",
            "reconciliation":
                "none",
            "target_actual_included":
                False,
        }

        sealed = seal_prediction_record(
            output_dir / "predictions",
            stem=prediction.prediction_id,
            record=record,
        )

        sealed_pairs.append(
            (
                prediction,
                sealed,
            )
        )

    seals = tuple(
        sealed
        for _, sealed
        in sealed_pairs
    )

    actual = reader.read_actual(
        game_id=game_id,
        target_draw_no=target_draw_no,
        expected_target_ds=target_ds,
        seals=seals,
    )

    scores = [
        _score_payload(
            game_id=game_id,
            target_draw_no=target_draw_no,
            target_ds=target_ds,
            actual=actual,
            sealed=sealed,
            prediction_id=
                prediction.prediction_id,
            predicted=prediction.values,
        )
        for prediction, sealed
        in sealed_pairs
    ]

    score_path = (
        output_dir
        / "SCORES.json"
    )

    score_sha = write_json_once(
        score_path,
        {
            "schema_version":
                "oof-baseline-target-scores.v1",
            "run_id":
                run_id,
            "game_id":
                game_id,
            "target_draw_no":
                target_draw_no,
            "target_ds":
                target_ds.isoformat(),
            "all_predictions_sealed_before_actual":
                True,
            "actual_read_at_utc":
                actual.actual_read_at_utc,
            "scores":
                scores,
        },
    )

    return TargetBundleResult(
        score_path=score_path,
        score_sha256=score_sha,
        seals=seals,
        actual_reveal=actual,
    )


def run_timer_target_bundle(
    *,
    reader: DevelopmentSnapshotReader,
    output_dir: Path,
    run_id: str,
    game_id: str,
    target_draw_no: int,
    target_ds: date,
    context_length: int,
    specs: Sequence[TimerPredictionSpec],
    predictor: TimerPredictor,
) -> TargetBundleResult:
    """Seal every Timer layout/seed prediction before actual reveal."""

    if not specs:
        raise ValueError(
            "Timer prediction specs must not be empty"
        )

    if output_dir.exists():
        raise FileExistsError(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    context = reader.read_context(
        game_id=game_id,
        target_draw_no=target_draw_no,
        context_length=context_length,
    )

    sealed_predictions: list[
        tuple[
            TimerPredictionSpec,
            TimerResponse,
            tuple[float, ...],
            SealedPrediction,
        ]
    ] = []

    for index, spec in enumerate(
        specs
    ):
        if _SAFE_ID.fullmatch(
            spec.candidate_id
        ) is None:
            raise ValueError(
                "unsafe candidate ID"
            )

        request_run_id = (
            f"{run_id}-d{target_draw_no}"
            f"-c{index}-s{spec.seed}"
        )

        if len(request_run_id) > 128:
            raise ValueError(
                "derived Timer run ID is too long"
            )

        artifact_paths = ArtifactPaths(
            request_path=(
                f"targets/{target_draw_no}/"
                f"{spec.candidate_id}/request.json"
            ),
            response_path=(
                f"targets/{target_draw_no}/"
                f"{spec.candidate_id}/response.json"
            ),
            snapshot_path=(
                "runtime/timer-base-84m/snapshot"
            ),
            manifest_path=(
                "runtime/timer-base-84m/manifest.json"
            ),
        )

        request = build_timer_request(
            context=context,
            game_id=game_id,
            spec=spec,
            request_run_id=request_run_id,
            artifact_paths=artifact_paths,
        )

        response = predictor(
            request
        )

        if response.status != "PREDICTED":
            raise RuntimeError(
                "Timer predictor did not return "
                "PREDICTED"
            )

        if response.actuals_used is not False:
            raise RuntimeError(
                "Timer response claims actual use"
            )

        if response.cpu_fallback is not False:
            raise RuntimeError(
                "Timer CPU fallback is forbidden"
            )

        prediction_array = np.asarray(
            response.point_forecast,
            dtype=float,
        )

        expected_positions = len(
            _position_columns(game_id)
        )

        if prediction_array.shape != (
            expected_positions,
            1,
        ):
            raise RuntimeError(
                "unexpected Timer prediction shape"
            )

        if not np.isfinite(
            prediction_array
        ).all():
            raise RuntimeError(
                "non-finite Timer prediction"
            )

        prediction = tuple(
            float(value)
            for value in prediction_array[
                :,
                0,
            ]
        )

        record = {
            "schema_version":
                "oof-timer-prediction.v1",
            "run_id":
                run_id,
            "prediction_id":
                spec.candidate_id,
            "candidate_type":
                "timer-base-84m",
            "game_id":
                game_id,
            "target_draw_no":
                target_draw_no,
            "target_ds_identity":
                target_ds.isoformat(),
            "target_layout":
                spec.target_layout,
            "seed":
                spec.seed,
            "requested_device":
                spec.requested_device,
            "prediction":
                list(prediction),
            "timer_prediction_sha256_f32":
                response.prediction_sha256_f32,
            "timer_response":
                response.model_dump(
                    mode="json"
                ),
            "post_processing":
                "raw_point_no_transform",
            "reconciliation":
                "none",
            "target_actual_included":
                False,
        }

        stem = (
            f"{spec.candidate_id}"
            f"-seed{spec.seed}"
        )

        sealed = seal_prediction_record(
            output_dir / "predictions",
            stem=stem,
            record=record,
        )

        sealed_predictions.append(
            (
                spec,
                response,
                prediction,
                sealed,
            )
        )

    seals = tuple(
        item[3]
        for item in sealed_predictions
    )

    actual = reader.read_actual(
        game_id=game_id,
        target_draw_no=target_draw_no,
        expected_target_ds=target_ds,
        seals=seals,
    )

    scores = []

    for (
        spec,
        response,
        prediction,
        sealed,
    ) in sealed_predictions:
        score = _score_payload(
            game_id=game_id,
            target_draw_no=target_draw_no,
            target_ds=target_ds,
            actual=actual,
            sealed=sealed,
            prediction_id=(
                f"{spec.candidate_id}"
                f"-seed{spec.seed}"
            ),
            predicted=prediction,
        )

        score[
            "timer_prediction_sha256_f32"
        ] = response.prediction_sha256_f32

        score[
            "target_layout"
        ] = spec.target_layout

        score["seed"] = spec.seed

        scores.append(score)

    score_path = (
        output_dir
        / "SCORES.json"
    )

    score_sha = write_json_once(
        score_path,
        {
            "schema_version":
                "oof-timer-target-scores.v1",
            "run_id":
                run_id,
            "game_id":
                game_id,
            "target_draw_no":
                target_draw_no,
            "target_ds":
                target_ds.isoformat(),
            "all_predictions_sealed_before_actual":
                True,
            "actual_read_at_utc":
                actual.actual_read_at_utc,
            "scores":
                scores,
        },
    )

    return TargetBundleResult(
        score_path=score_path,
        score_sha256=score_sha,
        seals=seals,
        actual_reveal=actual,
    )


def verify_target_bundle(
    result: TargetBundleResult,
) -> None:
    for sealed in result.seals:
        verify_sealed_prediction(
            sealed
        )

        if (
            result.actual_reveal
            .actual_read_at_utc
            < sealed.sealed_at_utc
        ):
            raise ValueError(
                "actual was read before prediction seal"
            )

    if (
        sha256_file(
            result.score_path
        )
        != result.score_sha256
    ):
        raise ValueError(
            "score artifact SHA mismatch"
        )
