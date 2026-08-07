from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict

from .contracts import Chronos2RequestV2, GameGeometry, PositionRange, SeriesLayout


class CompiledChronosInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    context_df: pd.DataFrame
    future_df: pd.DataFrame | None
    target: str | list[str]
    series_identity: tuple[str, ...]
    synthetic_timestamps: tuple[str, ...]
    source_history_sha256: str
    compiled_input_sha256: str


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def game_geometry_preset(game_id: str) -> tuple[GameGeometry, tuple[str, ...]]:
    normalized = game_id.lower().replace("-", "").replace("_", "")
    presets: dict[str, tuple[GameGeometry, tuple[str, ...]]] = {
        "numbers3": (
            GameGeometry(
                game_id="numbers3",
                position_count=3,
                candidate_min=0,
                candidate_max=9,
                allow_duplicates=True,
                sort_policy="preserve",
            ),
            ("n1", "n2", "n3"),
        ),
        "numbers4": (
            GameGeometry(
                game_id="numbers4",
                position_count=4,
                candidate_min=0,
                candidate_max=9,
                allow_duplicates=True,
                sort_policy="preserve",
            ),
            ("n1", "n2", "n3", "n4"),
        ),
        "miniloto": (
            GameGeometry(
                game_id="miniloto",
                position_count=5,
                candidate_min=1,
                candidate_max=31,
            ),
            tuple(f"n{i}" for i in range(1, 6)),
        ),
        "loto6": (
            GameGeometry(game_id="loto6", position_count=6, candidate_min=1, candidate_max=43),
            tuple(f"n{i}" for i in range(1, 7)),
        ),
        "loto7": (
            GameGeometry(game_id="loto7", position_count=7, candidate_min=1, candidate_max=37),
            tuple(f"n{i}" for i in range(1, 8)),
        ),
        "bingo5": (
            GameGeometry(
                game_id="bingo5",
                position_count=8,
                candidate_min=1,
                candidate_max=40,
                sort_policy="preserve",
                position_ranges={
                    f"n{i}": PositionRange(minimum=(i - 1) * 5 + 1, maximum=i * 5)
                    for i in range(1, 9)
                },
            ),
            tuple(f"n{i}" for i in range(1, 9)),
        ),
    }
    try:
        return presets[normalized]
    except KeyError as exc:
        raise KeyError(f"unsupported game preset: {game_id}") from exc


def _validate_history(request: Chronos2RequestV2) -> None:
    previous_draw: int | None = None
    previous_date: datetime | None = None
    seen_draws: set[int] = set()
    for index, row in enumerate(request.history):
        missing = [name for name in request.position_columns if name not in row]
        if missing:
            raise ValueError(f"history row {index} is missing position columns: {missing}")
        if "draw_no" not in row or "draw_date" not in row:
            raise ValueError(f"history row {index} requires draw_no and draw_date")
        try:
            draw_no = int(row["draw_no"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"history row {index} draw_no is not an integer") from exc
        if draw_no in seen_draws or (previous_draw is not None and draw_no <= previous_draw):
            raise ValueError("draw_no must be unique and strictly increasing")
        seen_draws.add(draw_no)
        previous_draw = draw_no
        try:
            draw_date = pd.Timestamp(row["draw_date"]).to_pydatetime()
        except Exception as exc:
            raise ValueError(f"history row {index} draw_date is invalid") from exc
        if previous_date is not None and draw_date <= previous_date:
            raise ValueError("draw_date must be strictly increasing")
        previous_date = draw_date

        values: list[float] = []
        for name in request.position_columns:
            try:
                value = float(row[name])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"history row {index} {name!r} is not numeric") from exc
            if not math.isfinite(value):
                raise ValueError(f"history row {index} {name!r} is not finite")
            value_range = request.game_geometry.position_ranges.get(name)
            lower = value_range.minimum if value_range else request.game_geometry.candidate_min
            upper = value_range.maximum if value_range else request.game_geometry.candidate_max
            if value < lower or value > upper:
                raise ValueError(
                    f"history row {index} {name!r}={value} is outside [{lower}, {upper}]"
                )
            values.append(value)
        if not request.game_geometry.allow_duplicates and len(values) != len(set(values)):
            raise ValueError(f"history row {index} contains duplicate position values")
        if request.game_geometry.sort_policy == "ascending" and values != sorted(values):
            raise ValueError(f"history row {index} values are not ascending")


def compile_chronos_input(request: Chronos2RequestV2) -> CompiledChronosInput:
    _validate_history(request)
    base = datetime(2000, 1, 1, tzinfo=timezone.utc)
    timestamps = [base + timedelta(days=index) for index in range(len(request.history))]
    past_covariates = request.past_covariates or tuple({} for _ in request.history)

    records: list[dict[str, Any]] = []
    if request.series_layout in {SeriesLayout.POSITION_LOCAL, SeriesLayout.POSITION_PANEL}:
        for source_index, (row, covariates) in enumerate(
            zip(request.history, past_covariates, strict=True)
        ):
            for name in request.position_columns:
                record = {
                    "item_id": name,
                    "timestamp": timestamps[source_index],
                    "target": float(row[name]),
                }
                record.update(covariates)
                records.append(record)
        context_df = pd.DataFrame.from_records(records)
        target: str | list[str] = "target"
        series_identity = request.position_columns
    else:
        for source_index, (row, covariates) in enumerate(
            zip(request.history, past_covariates, strict=True)
        ):
            record = {
                "item_id": request.game_geometry.game_id,
                "timestamp": timestamps[source_index],
            }
            record.update({name: float(row[name]) for name in request.position_columns})
            record.update(covariates)
            records.append(record)
        context_df = pd.DataFrame.from_records(records)
        target = list(request.position_columns)
        series_identity = request.position_columns

    future_df: pd.DataFrame | None = None
    if request.future_covariates:
        future_records: list[dict[str, Any]] = []
        future_timestamps = [
            timestamps[-1] + timedelta(days=step)
            for step in range(1, request.prediction_length + 1)
        ]
        if request.series_layout in {SeriesLayout.POSITION_LOCAL, SeriesLayout.POSITION_PANEL}:
            for step, covariates in enumerate(request.future_covariates):
                for name in request.position_columns:
                    future_records.append(
                        {
                            "item_id": name,
                            "timestamp": future_timestamps[step],
                            **covariates,
                        }
                    )
        else:
            for step, covariates in enumerate(request.future_covariates):
                future_records.append(
                    {
                        "item_id": request.game_geometry.game_id,
                        "timestamp": future_timestamps[step],
                        **covariates,
                    }
                )
        future_df = pd.DataFrame.from_records(future_records)

    compiled_payload = {
        "context": context_df.to_dict(orient="records"),
        "future": None if future_df is None else future_df.to_dict(orient="records"),
        "target": target,
        "series_identity": series_identity,
    }
    return CompiledChronosInput(
        context_df=context_df,
        future_df=future_df,
        target=target,
        series_identity=series_identity,
        synthetic_timestamps=tuple(value.isoformat() for value in timestamps),
        source_history_sha256=_canonical_sha256(request.history),
        compiled_input_sha256=_canonical_sha256(compiled_payload),
    )
