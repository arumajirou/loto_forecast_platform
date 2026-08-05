from datetime import datetime, timezone

import numpy as np

from loto.moirai2_campaign.time_adapter import (
    build_calendar_time_axis,
    build_draw_sequence_axis,
)


def test_draw_sequence_mapping_is_deterministic() -> None:
    target = np.arange(15, dtype=np.float32).reshape(3, 5)
    first = build_draw_sequence_axis(target, [101, 102, 103, 104, 105])
    second = build_draw_sequence_axis(target, [101, 102, 103, 104, 105])
    assert first.mapping_sha256 == second.mapping_sha256
    assert first.frequency_policy == "one_period_per_draw"


def test_calendar_axis_preserves_missing_dates_as_nan() -> None:
    target = np.asarray([[1.0, 3.0], [2.0, 4.0]], dtype=np.float32)
    timestamps = [
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 3, tzinfo=timezone.utc),
    ]
    axis = build_calendar_time_axis(target, timestamps)
    assert axis.target.shape == (2, 3)
    assert np.isnan(axis.target[:, 1]).all()
    assert axis.missing_period_policy == "preserve_as_nan"


def test_draw_sequence_rejects_gaps() -> None:
    target = np.arange(9, dtype=np.float32).reshape(3, 3)
    try:
        build_draw_sequence_axis(target, [10, 11, 13])
    except ValueError as exc:
        assert "gap-free" in str(exc)
    else:
        raise AssertionError("gap in draw sequence was accepted")
