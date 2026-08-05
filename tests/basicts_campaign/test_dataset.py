from __future__ import annotations

import pytest

from loto.basicts_campaign.dataset import GameGeometry, build_windows, compile_wide_rows


def geometry() -> GameGeometry:
    return GameGeometry(
        game_id="numbers3",
        position_columns=("n1", "n2", "n3"),
        minimum_value=0,
        maximum_value=9,
    )


def test_compile_and_window_preserves_identity() -> None:
    rows = [
        {
            "draw_no": draw,
            "draw_date": f"2026-01-{draw:02d}",
            "n1": draw,
            "n2": 2,
            "n3": 3,
        }
        for draw in range(1, 7)
    ]
    values, identity = compile_wide_rows(rows, geometry())
    windowed = build_windows(values, identity, input_len=3, output_len=1)
    assert windowed.inputs.shape == (3, 3, 3)
    assert windowed.targets.shape == (3, 1, 3)
    assert windowed.sample_identity[0]["input_last_draw_no"] == 3
    assert windowed.sample_identity[0]["target_draw_nos"] == [4]


def test_compile_rejects_unordered_or_gapped_draws() -> None:
    unordered = [
        {"draw_no": 2, "n1": 1, "n2": 2, "n3": 3},
        {"draw_no": 1, "n1": 1, "n2": 2, "n3": 3},
    ]
    with pytest.raises(ValueError, match="ordered"):
        compile_wide_rows(unordered, geometry())

    gapped = [
        {"draw_no": 1, "n1": 1, "n2": 2, "n3": 3},
        {"draw_no": 3, "n1": 1, "n2": 2, "n3": 3},
    ]
    with pytest.raises(ValueError, match="gap-free"):
        compile_wide_rows(gapped, geometry())
