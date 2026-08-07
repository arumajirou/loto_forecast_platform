from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loto.adapters.tirex2.contracts import GameGeometry, SeriesLayout, Tirex2Request


def schema_v1_to_v2(payload: dict[str, Any]) -> Tirex2Request:
    """Convert the legacy seven-column request into the strict v2 contract."""
    history = payload.get("history")
    if not isinstance(history, list) or not history:
        raise ValueError("schema-v1 history must be a non-empty row list")
    target_columns = [f"n{position}" for position in range(1, 8)]
    target_history = [[float(row[column]) for row in history] for column in target_columns]
    return Tirex2Request(
        run_id=str(payload.get("run_id", "legacy-v1")),
        game_geometry=GameGeometry(
            game_id=str(payload.get("game_id", "loto7")),
            position_count=7,
            candidate_min=int(payload.get("candidate_min", 1)),
            candidate_max=int(payload.get("candidate_max", 37)),
            strictly_increasing=True,
        ),
        series_layout=SeriesLayout.POSITION_JOINT_MULTIVARIATE,
        target_columns=target_columns,
        target_history=target_history,
        prediction_issue_time=datetime.now(UTC),
        context_length=len(history),
        prediction_length=int(payload.get("prediction_length", 1)),
        device=str(payload.get("device", "cpu")),
        snapshot_path=payload.get("snapshot_path"),
    )
