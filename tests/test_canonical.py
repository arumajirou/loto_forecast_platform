import pandas as pd
import pytest

from loto.data.canonical import CanonicalDataError, canonicalize_loto7, to_candidate_table, to_position_table


def _valid_df():
    return pd.DataFrame(
        [
            {"draw_no": 1, "draw_date": "2026-01-01", "n1": 1, "n2": 5, "n3": 9, "n4": 13, "n5": 20, "n6": 25, "n7": 37},
            {"draw_no": 2, "draw_date": "2026-01-08", "n1": 2, "n2": 6, "n3": 10, "n4": 14, "n5": 21, "n6": 26, "n7": 36},
        ]
    )


def test_canonicalize_rejects_non_ascending_draw():
    df = _valid_df()
    df.loc[0, "n4"] = 8
    with pytest.raises(CanonicalDataError):
        canonicalize_loto7(df)


def test_canonical_tables_have_expected_row_counts():
    master, manifest = canonicalize_loto7(_valid_df())
    assert manifest.row_count == 2
    assert len(to_position_table(master)) == 14
    candidates = to_candidate_table(master)
    assert len(candidates) == 74
    assert candidates.groupby("draw_id")["selected"].sum().tolist() == [7, 7]
