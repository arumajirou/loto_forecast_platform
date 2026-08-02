from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.operations.sync_numbers3_n1_from_postgres import (
    atomic_write_parquet,
    validate,
)


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ds": pd.date_range(
                "2000-01-01",
                periods=7001,
                freq="D",
            ),
            "y": [index % 10 for index in range(7001)],
        }
    )


def test_validate_accepts_valid_numbers3_n1() -> None:
    validate(valid_frame())


def test_validate_rejects_duplicate_ds() -> None:
    frame = valid_frame()
    frame.loc[1, "ds"] = frame.loc[0, "ds"]

    with pytest.raises(
        ValueError,
        match="Duplicate ds",
    ):
        validate(frame)


def test_validate_rejects_non_integer_y() -> None:
    frame = valid_frame()
    frame["y"] = frame["y"].astype(float)
    frame.loc[0, "y"] = 1.5

    with pytest.raises(
        ValueError,
        match="Non-integer",
    ):
        validate(frame)


def test_validate_rejects_out_of_range_y() -> None:
    frame = valid_frame()
    frame.loc[0, "y"] = 10

    with pytest.raises(
        ValueError,
        match="outside 0..9",
    ):
        validate(frame)


def test_atomic_write_skips_semantically_equal_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "numbers3_n1.parquet"
    frame = valid_frame()

    first_changed, first_hash = atomic_write_parquet(
        frame,
        target,
    )

    first_mtime = target.stat().st_mtime_ns

    second_changed, second_hash = atomic_write_parquet(
        frame.copy(),
        target,
    )

    second_mtime = target.stat().st_mtime_ns

    assert first_changed is True
    assert second_changed is False
    assert first_hash == second_hash
    assert first_mtime == second_mtime


def test_atomic_write_roundtrip(
    tmp_path: Path,
) -> None:
    target = tmp_path / "numbers3_n1.parquet"
    frame = valid_frame()

    changed, output_hash = atomic_write_parquet(
        frame,
        target,
    )

    assert changed is True
    assert target.is_file()
    assert len(output_hash) == 64

    actual = pd.read_parquet(target)

    assert len(actual) == len(frame)
    assert actual["ds"].is_monotonic_increasing
    assert actual["ds"].duplicated().sum() == 0
