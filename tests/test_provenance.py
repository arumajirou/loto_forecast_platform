"""The v2.1.0 quality gate passed with 100% null provenance. This gate does not."""

import pandas as pd

from loto.data.provenance import REQUIRED_PROVENANCE_COLUMNS, check_provenance


def _good(n=3):
    return pd.DataFrame(
        {
            "game": ["loto7"] * n,
            "game_display_name": ["ロト7"] * n,
            "source_url": ["https://example.invalid/csv/loto7"] * n,
            "draw_no": list(range(1, n + 1)),
            "draw_date": pd.to_datetime(["2026-01-02", "2026-01-09", "2026-01-16"][:n]),
        }
    )


def test_complete_provenance_passes():
    assert check_provenance(_good()).status == "PASS"


def test_the_exact_v2_defect_is_caught():
    """All six games shipped with game / game_display_name / source_url fully null."""
    frame = _good()
    for column in ("game", "game_display_name", "source_url"):
        frame[column] = None
    report = check_provenance(frame)
    assert report.status == "FAIL"
    kinds = {(i.column, i.kind) for i in report.issues}
    assert ("game", "null_values") in kinds
    assert ("source_url", "null_values") in kinds


def test_missing_column_is_distinguished_from_null_values():
    frame = _good().drop(columns=["source_url"])
    kinds = {(i.column, i.kind) for i in check_provenance(frame).issues}
    assert ("source_url", "missing_column") in kinds


def test_partial_nulls_are_counted():
    frame = _good()
    frame.loc[0, "game"] = None
    issue = next(i for i in check_provenance(frame).issues if i.column == "game")
    assert issue.n_affected == 1


def test_blank_strings_are_caught_separately_from_nulls():
    frame = _good()
    frame["source_url"] = ["", "x", "x"]
    kinds = {i.kind for i in check_provenance(frame).issues if i.column == "source_url"}
    assert "blank_values" in kinds


def test_inconsistent_constant_column_is_caught():
    frame = _good()
    frame["game"] = ["loto7", "loto6", "loto7"]
    kinds = {i.kind for i in check_provenance(frame).issues if i.column == "game"}
    assert "inconsistent" in kinds


def test_expected_game_mismatch_is_caught():
    report = check_provenance(_good(), expected_game="loto6")
    assert any(i.kind == "mismatch" for i in report.issues)


def test_empty_frame_is_not_silently_ok():
    report = check_provenance(pd.DataFrame())
    assert report.status == "FAIL"


def test_required_columns_are_declared():
    assert "source_url" in REQUIRED_PROVENANCE_COLUMNS
    assert "game" in REQUIRED_PROVENANCE_COLUMNS
