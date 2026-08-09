from __future__ import annotations

import runpy
from pathlib import Path

import pandas as pd
import pytest

from loto.toto2_campaign import raw_history_export, raw_history_verify
from loto.toto2_campaign.raw_history_export import (
    FORMAL_GAMES,
    PHYSICAL_GAME_IDS,
    PHYSICAL_GAME_TO_LOGICAL,
    build_exports,
    build_game_export,
    normalize_game_id,
    parse_checksum_lines,
    position_number,
)


def make_game_frame(game_id: str, rows: int = 512) -> pd.DataFrame:
    specs = {
        "numbers3": (3, 0),
        "numbers4": (4, 0),
        "miniloto": (5, 1),
        "loto6": (6, 1),
        "loto7": (7, 1),
    }
    count, start = specs[game_id]
    records = []
    dates = pd.date_range("2020-01-01", periods=rows, freq="D")
    for draw_index, ds in enumerate(dates):
        for position in range(1, count + 1):
            if game_id.startswith("numbers"):
                value = (draw_index + position) % 10
            else:
                value = start + position - 1
            records.append(
                {
                    "game_id": game_id,
                    "ds": ds,
                    "unique_id": f"{game_id}::raw::n{position}",
                    "y": value,
                }
            )
    return pd.DataFrame.from_records(records)


def test_position_number_accepts_current_and_qualified_ids() -> None:
    assert position_number("N1") == 1
    assert position_number("loto7::raw::n7") == 7
    with pytest.raises(ValueError):
        position_number("position-seven")


def test_physical_game_id_contract_maps_mini_to_miniloto() -> None:
    assert PHYSICAL_GAME_TO_LOGICAL["mini"] == "miniloto"
    assert tuple(PHYSICAL_GAME_TO_LOGICAL) == PHYSICAL_GAME_IDS
    assert normalize_game_id("mini") == "miniloto"
    assert normalize_game_id(" Mini ") == "miniloto"

    logical_games = {normalize_game_id(game_id) for game_id in PHYSICAL_GAME_IDS}

    assert logical_games == set(FORMAL_GAMES)


def test_build_exports_accepts_physical_mini_identifier() -> None:
    source = pd.concat(
        [make_game_frame(game) for game in FORMAL_GAMES],
        ignore_index=True,
    )

    source.loc[
        source["game_id"] == "miniloto",
        "game_id",
    ] = "mini"

    exports = build_exports(source)

    assert list(exports) == list(FORMAL_GAMES)
    assert exports["miniloto"].statistics["draw_count"] == 512
    assert exports["miniloto"].json_payload["game_id"] == "miniloto"


def test_db_export_query_uses_physical_mini_and_logical_miniloto() -> None:
    root = Path(__file__).resolve().parents[2]
    namespace = runpy.run_path(
        str(root / "scripts" / "export_toto2_4m_raw_history.py"),
        run_name="toto2_raw_history_export_script",
    )

    query = namespace["QUERY_TEXT"]

    assert "WHEN 'mini' THEN 'miniloto'" in query
    assert (
        "WHERE LOWER(TRIM(loto::text)) IN "
        "('numbers3', 'numbers4', 'mini', 'loto6', 'loto7')" in query
    )
    assert "LOWER(TRIM(ts_type::text)) = 'raw'" in query


def test_build_game_export_creates_gap_free_ordinal_draws() -> None:
    export = build_game_export("loto7", make_game_frame("loto7"))
    assert export.json_payload["rows"][0]["draw_no"] == 1
    assert export.json_payload["rows"][-1]["draw_no"] == 512
    assert export.audit_frame["ds"].iloc[0] == "2020-01-01"
    assert export.statistics["draw_no_semantics"] == "one_based_ordinal_over_ds"


def test_build_exports_requires_all_formal_games() -> None:
    source = pd.concat([make_game_frame(game) for game in FORMAL_GAMES], ignore_index=True)
    exports = build_exports(source)
    assert list(exports) == list(FORMAL_GAMES)
    assert all(export.statistics["draw_count"] == 512 for export in exports.values())


def test_duplicate_position_is_rejected() -> None:
    frame = make_game_frame("numbers3")
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        build_game_export("numbers3", frame)


def test_incomplete_draw_is_rejected() -> None:
    frame = make_game_frame("numbers4")
    frame = frame.drop(frame.index[0]).reset_index(drop=True)
    with pytest.raises(ValueError, match="incomplete"):
        build_game_export("numbers4", frame)


def test_non_integer_and_order_violations_are_rejected() -> None:
    numbers = make_game_frame("numbers3").astype({"y": "float64"})
    numbers.loc[0, "y"] = 1.5
    with pytest.raises(ValueError, match="non-integer"):
        build_game_export("numbers3", numbers)

    lottery = make_game_frame("loto7")
    first_date = lottery.loc[0, "ds"]
    mask = lottery["ds"] == first_date
    lottery.loc[mask, "y"] = [1, 2, 3, 4, 5, 7, 6]
    with pytest.raises(ValueError, match="strictly increasing"):
        build_game_export("loto7", lottery)


def test_checksum_parser_rejects_duplicates_and_invalid_paths(tmp_path: Path) -> None:
    digest = "a" * 64
    assert parse_checksum_lines([f"{digest}  file.json"]) == {"file.json": digest}
    with pytest.raises(ValueError, match="duplicate"):
        parse_checksum_lines([f"{digest}  file.json", f"{digest}  file.json"])
    with pytest.raises(ValueError, match="invalid"):
        parse_checksum_lines([f"{digest}  ../file.json"])


def test_bundle_writer_and_verifier_reject_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = pd.concat([make_game_frame(game) for game in FORMAL_GAMES], ignore_index=True)
    exports = build_exports(source)

    def fake_to_parquet(self, path, **kwargs):
        del kwargs
        self.to_csv(path, index=False)

    def fake_read_parquet(path, **kwargs):
        del kwargs
        return pd.read_csv(path)

    monkeypatch.setattr(raw_history_export, "_parquet_metadata", lambda: {"engine": "fake"})
    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet)
    monkeypatch.setattr(raw_history_verify.pd, "read_parquet", fake_read_parquet)

    snapshot = {
        "transaction_read_only": True,
        "transaction_isolation": "repeatable read",
    }
    root = tmp_path / "export"
    raw_history_export.write_export_bundle(
        exports,
        output_root=root,
        database_snapshot=snapshot,
        query_text="SELECT 1;\n",
    )
    result = raw_history_verify.verify_export_bundle(root)
    assert result["status"] == "VERIFIED"
    assert len(result["games"]) == 5

    with (root / "numbers3.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="SHA-256"):
        raw_history_verify.verify_export_bundle(root)
