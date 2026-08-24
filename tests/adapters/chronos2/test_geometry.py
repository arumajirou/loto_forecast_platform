from __future__ import annotations

import pytest

from loto.adapters.chronos2.contracts import Chronos2RequestV2
from loto.adapters.chronos2.geometry import compile_chronos_input, game_geometry_preset
from loto.adapters.chronos2.manifest import CHRONOS_MODEL_REVISION


def make_payload(game_id: str, layout: str = "position_local") -> dict[str, object]:
    geometry, columns = game_geometry_preset(game_id)
    history = []
    for index in range(3):
        row: dict[str, object] = {
            "draw_no": index + 1,
            "draw_date": f"2026-02-{index + 1:02d}",
        }
        if game_id == "bingo5":
            for position, column in enumerate(columns, start=1):
                row[column] = (position - 1) * 5 + 1 + index
        elif game_id in {"numbers3", "numbers4"}:
            for position, column in enumerate(columns):
                row[column] = (position + index) % 10
        else:
            for position, column in enumerate(columns, start=1):
                row[column] = position + index
        history.append(row)
    return {
        "schema_version": 2,
        "run_id": f"geometry-{game_id}-{layout}",
        "revision": CHRONOS_MODEL_REVISION,
        "game_geometry": geometry.model_dump(mode="json"),
        "series_layout": layout,
        "position_columns": columns,
        "history": history,
        "context_length": 3,
        "prediction_length": 2,
        "quantile_levels": [0.1, 0.5, 0.9],
        "cross_learning": layout == "position_panel",
        "device": "cpu",
        "local_files_only": True,
    }


@pytest.mark.parametrize(
    "game_id", ["numbers3", "numbers4", "miniloto", "loto6", "loto7", "bingo5"]
)
def test_all_game_geometries_compile(game_id: str) -> None:
    request = Chronos2RequestV2.model_validate(make_payload(game_id))
    compiled = compile_chronos_input(request)
    assert len(compiled.context_df) == len(request.history) * request.game_geometry.position_count
    assert compiled.series_identity == request.position_columns


def test_multivariate_compiles_wide_targets() -> None:
    request = Chronos2RequestV2.model_validate(
        make_payload("loto7", layout="position_multivariate")
    )
    compiled = compile_chronos_input(request)
    assert len(compiled.context_df) == len(request.history)
    assert compiled.target == list(request.position_columns)


def test_future_covariates_are_known_future_only() -> None:
    payload = make_payload("numbers3")
    payload["past_covariates"] = [
        {"weekday": 1, "month": 1},
        {"weekday": 2, "month": 1},
        {"weekday": 3, "month": 1},
    ]
    payload["future_covariates"] = [
        {"weekday": 1, "month": 2},
        {"weekday": 2, "month": 2},
    ]
    request = Chronos2RequestV2.model_validate(payload)
    compiled = compile_chronos_input(request)
    assert compiled.future_df is not None
    assert len(compiled.future_df) == request.game_geometry.position_count * 2


def test_duplicate_draw_number_is_rejected() -> None:
    payload = make_payload("loto7")
    payload["history"][1]["draw_no"] = 1  # type: ignore[index]
    request = Chronos2RequestV2.model_validate(payload)
    with pytest.raises(ValueError, match="strictly increasing"):
        compile_chronos_input(request)


def test_bingo5_position_range_is_enforced() -> None:
    payload = make_payload("bingo5")
    payload["history"][0]["n1"] = 6  # type: ignore[index]
    request = Chronos2RequestV2.model_validate(payload)
    with pytest.raises(ValueError, match=r"outside \[1, 5\]"):
        compile_chronos_input(request)



def test_compiled_timestamps_are_numpy_int64_view_safe() -> None:
    request = Chronos2RequestV2.model_validate(
        make_payload(
            "loto7",
            layout="position_multivariate",
        )
    )

    compiled = compile_chronos_input(request)

    timestamps = compiled.context_df["timestamp"]

    assert timestamps.dt.tz is None

    array = timestamps.to_numpy()

    assert array.dtype.kind == "M"

    viewed = array.view("int64")

    assert viewed.shape == array.shape
