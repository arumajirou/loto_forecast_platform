from __future__ import annotations

import pytest

from loto.adapters.autogluon.contracts import GameGeometry
from loto.adapters.autogluon.geometry import compile_regular_history


def _geometry(positions: int) -> GameGeometry:
    return GameGeometry(
        game_id=f"fixture-{positions}",
        position_columns=tuple(f"n{i}" for i in range(1, positions + 1)),
        candidate_min=0,
        candidate_max=99,
        selection_count=positions,
    )


def _history(positions: int, rows: int = 2) -> list[dict[str, object]]:
    return [
        {
            "draw_no": row + 1,
            "draw_date": f"2026-01-{row + 1:02d}",
            **{f"n{i}": i + row for i in range(1, positions + 1)},
        }
        for row in range(rows)
    ]


@pytest.mark.parametrize("positions", [3, 4, 5, 6, 7])
def test_geometry_is_not_hardcoded_to_seven_positions(positions: int) -> None:
    compiled = compile_regular_history(_history(positions), _geometry(positions))
    assert len(compiled.records) == positions * 2
    assert {row["item_id"] for row in compiled.records} == {
        f"position-{index}" for index in range(1, positions + 1)
    }
    assert len(compiled.timeline_mapping) == 2


def test_timeline_mapping_and_hashes_are_deterministic() -> None:
    geometry = _geometry(3)
    first = compile_regular_history(_history(3), geometry)
    second = compile_regular_history(_history(3), geometry)
    assert first.source_order_sha256 == second.source_order_sha256
    assert first.mapping_sha256 == second.mapping_sha256
    assert first.geometry_sha256 == second.geometry_sha256
    assert first.timeline_mapping[0].synthetic_timestamp.startswith("2000-01-01")


def test_duplicate_source_order_is_rejected() -> None:
    history = _history(3)
    history[1]["draw_no"] = history[0]["draw_no"]
    with pytest.raises(ValueError, match="source order values must be unique"):
        compile_regular_history(history, _geometry(3))


def test_missing_position_is_rejected() -> None:
    history = _history(3)
    del history[0]["n3"]
    with pytest.raises(ValueError, match="missing position columns"):
        compile_regular_history(history, _geometry(3))


def test_unsorted_values_are_rejected_without_silent_reordering() -> None:
    history = _history(3)
    history[0]["n1"], history[0]["n2"] = history[0]["n2"], history[0]["n1"]
    with pytest.raises(ValueError, match="not ascending"):
        compile_regular_history(history, _geometry(3))
