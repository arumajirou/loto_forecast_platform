from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.chronos2.contracts import Chronos2RequestV2
from loto.adapters.chronos2.geometry import game_geometry_preset
from loto.adapters.chronos2.manifest import CHRONOS_MODEL_REVISION


def history(columns: tuple[str, ...], rows: int = 3) -> list[dict[str, object]]:
    result = []
    for index in range(rows):
        row: dict[str, object] = {
            "draw_no": index + 1,
            "draw_date": f"2026-01-{index + 1:02d}",
        }
        for position, column in enumerate(columns, start=1):
            row[column] = position + index
        result.append(row)
    return result


def request_payload(game_id: str = "loto7", horizon: int = 1) -> dict[str, object]:
    geometry, columns = game_geometry_preset(game_id)
    return {
        "schema_version": 2,
        "run_id": f"test-{game_id}-{horizon}",
        "operation": "predict",
        "revision": CHRONOS_MODEL_REVISION,
        "game_geometry": geometry.model_dump(mode="json"),
        "series_layout": "position_local",
        "position_columns": columns,
        "history": history(columns),
        "prediction_length": horizon,
        "context_length": 2,
        "quantile_levels": [0.1, 0.5, 0.9],
        "cross_learning": False,
        "local_files_only": True,
        "device": "cpu",
    }


@pytest.mark.parametrize("horizon", [1, 2, 5])
def test_horizons_are_accepted(horizon: int) -> None:
    request = Chronos2RequestV2.model_validate(request_payload(horizon=horizon))
    assert request.prediction_length == horizon


@pytest.mark.parametrize(
    ("game_id", "count"),
    [
        ("numbers3", 3),
        ("numbers4", 4),
        ("miniloto", 5),
        ("loto6", 6),
        ("loto7", 7),
        ("bingo5", 8),
    ],
)
def test_game_presets_have_expected_position_count(game_id: str, count: int) -> None:
    geometry, columns = game_geometry_preset(game_id)
    assert geometry.position_count == count
    assert len(columns) == count


def test_unknown_argument_is_rejected() -> None:
    payload = request_payload()
    payload["silently_ignored"] = True
    with pytest.raises(ValidationError, match="silently_ignored"):
        Chronos2RequestV2.model_validate(payload)


def test_panel_requires_cross_learning() -> None:
    payload = request_payload()
    payload["series_layout"] = "position_panel"
    with pytest.raises(ValidationError, match="position_panel requires cross_learning=true"):
        Chronos2RequestV2.model_validate(payload)


def test_local_rejects_cross_learning() -> None:
    payload = request_payload()
    payload["cross_learning"] = True
    with pytest.raises(ValidationError, match="position_local requires cross_learning=false"):
        Chronos2RequestV2.model_validate(payload)


def test_local_files_only_is_fail_closed() -> None:
    payload = request_payload()
    payload["local_files_only"] = False
    with pytest.raises(ValidationError):
        Chronos2RequestV2.model_validate(payload)


def test_revision_requires_full_commit() -> None:
    payload = request_payload()
    payload["revision"] = "29ec376"
    with pytest.raises(ValidationError, match="40-character"):
        Chronos2RequestV2.model_validate(payload)


def test_reserved_covariate_key_is_rejected() -> None:
    payload = request_payload()
    payload["past_covariates"] = [
        {"target": 1},
        {"target": 2},
        {"target": 3},
    ]
    with pytest.raises(ValidationError, match="reserved keys"):
        Chronos2RequestV2.model_validate(payload)


def test_future_covariates_require_past_schema() -> None:
    payload = request_payload(horizon=2)
    payload["future_covariates"] = [{"weekday": 1}, {"weekday": 2}]
    with pytest.raises(ValidationError, match="require matching past_covariates"):
        Chronos2RequestV2.model_validate(payload)


def test_covariate_rows_require_one_schema() -> None:
    payload = request_payload()
    payload["past_covariates"] = [
        {"weekday": 1},
        {"weekday": 2, "month": 1},
        {"weekday": 3},
    ]
    with pytest.raises(ValidationError, match="schema differs"):
        Chronos2RequestV2.model_validate(payload)
