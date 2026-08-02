import pandas as pd
import pytest

from src.data_access import loto_repository as lr


def test_validate_table_name_ok():
    # private 関数だが、テーブル名バリデーションの動作確認
    name = lr._validate_table_name("nf_loto_final")
    assert name == "nf_loto_final"


def test_validate_table_name_rejects_invalid():
    with pytest.raises(ValueError):
        lr._validate_table_name("nf_loto;DROP TABLE x;")


def test_list_loto_tables_calls_read_sql(monkeypatch):
    calls = {}

    class DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_get_connection():
        return DummyConn()

    def fake_read_sql(query, conn):
        calls["query"] = query
        calls["conn"] = conn
        return pd.DataFrame({"tablename": ["nf_loto_final"]})

    monkeypatch.setattr(lr, "get_connection", fake_get_connection)
    monkeypatch.setattr(lr.pd, "read_sql", fake_read_sql)

    df = lr.list_loto_tables()
    assert "nf_loto_final" in df["tablename"].tolist()
    assert "nf_loto" in calls["query"]


def test_load_panel_by_loto_missing_required_cols_raises(monkeypatch):
    # 必須カラムが足りない場合に ValueError になることを確認
    class DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_get_connection():
        return DummyConn()

    def fake_read_sql(query, conn, params=None):
        # unique_id, ds, y のうち y をわざと欠落させる
        return pd.DataFrame(
            {
                "unique_id": ["N1", "N1"],
                "ds": pd.date_range("2020-01-01", periods=2),
            }
        )

    monkeypatch.setattr(lr, "get_connection", fake_get_connection)
    monkeypatch.setattr(lr.pd, "read_sql", fake_read_sql)

    with pytest.raises(ValueError):
        lr.load_panel_by_loto("nf_loto_final", "bingo5", ["N1"])


def test_load_panel_by_loto_ok(monkeypatch):
    # 必須カラムが揃っている場合に DataFrame がそのまま返ることを確認
    class DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_get_connection():
        return DummyConn()

    def fake_read_sql(query, conn, params=None):
        return pd.DataFrame(
            {
                "unique_id": ["N1", "N1", "N2"],
                "ds": pd.date_range("2020-01-01", periods=3),
                "y": [1.0, 2.0, 3.0],
                "hist_x": [0.1, 0.2, 0.3],
                "stat_s": [1, 1, 2],
                "futr_f": [10, 11, 12],
            }
        )

    monkeypatch.setattr(lr, "get_connection", fake_get_connection)
    monkeypatch.setattr(lr.pd, "read_sql", fake_read_sql)

    df = lr.load_panel_by_loto("nf_loto_final", "bingo5", ["N1", "N2"])
    assert set(["unique_id", "ds", "y"]).issubset(df.columns)
    assert len(df) == 3
