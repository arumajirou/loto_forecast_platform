import pandas as pd
import pytest

from loto.statsforecast.contracts import GameGeometry
from loto.statsforecast.data import build_long_panel, chronological_split


def geometry() -> GameGeometry:
    return GameGeometry(
        game="numbers3",
        positions=("d1", "d2", "d3"),
        candidate_min=0,
        candidate_max=9,
        top_k=3,
    )


def raw(rows: int = 8) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": range(1, rows + 1),
            "d1": [value % 10 for value in range(rows)],
            "d2": [(value + 1) % 10 for value in range(rows)],
            "d3": [(value + 2) % 10 for value in range(rows)],
        }
    )


def test_build_long_panel_preserves_raw_and_geometry() -> None:
    source = raw()
    before = source.copy(deep=True)
    panel = build_long_panel(source, geometry())
    pd.testing.assert_frame_equal(source, before)
    assert list(panel.columns) == ["unique_id", "ds", "y"]
    assert len(panel) == 24
    assert panel["unique_id"].nunique() == 3


def test_draw_sequence_rejects_gaps() -> None:
    source = raw()
    source.loc[4:, "draw_no"] += 1
    with pytest.raises(ValueError, match="gap-free"):
        build_long_panel(source, geometry())


def test_chronological_split_is_disjoint() -> None:
    panel = build_long_panel(raw(10), geometry())
    train, validation, holdout = chronological_split(
        panel,
        validation_size=2,
        holdout_size=2,
    )
    for unique_id in panel["unique_id"].unique():
        train_ds = train.loc[train.unique_id == unique_id, "ds"]
        val_ds = validation.loc[validation.unique_id == unique_id, "ds"]
        holdout_ds = holdout.loc[holdout.unique_id == unique_id, "ds"]
        assert train_ds.max() < val_ds.min() < holdout_ds.min()
