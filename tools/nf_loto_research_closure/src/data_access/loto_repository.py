"""
PostgreSQL 上の nf_loto% テーブルにアクセスするためのユーティリティ。

- nf_loto% テーブル構成の想定:
    - loto:       TEXT      (ロト種別)
    - num:        INTEGER   (回号)
    - ds:         DATE/TIMESTAMP (日付)
    - unique_id:  TEXT      (系列ID, N1/N2/... 等)
    - y:          NUMERIC   (目的変数)
    - その他:     外生変数 (hist_*, stat_*, futr_* 接頭辞付き)
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

import pandas as pd
import psycopg2

from config.db_config import DB_CONFIG


def get_connection():
    """psycopg2 接続を返すシンプルなヘルパー。"""
    return psycopg2.connect(**DB_CONFIG)


def _validate_table_name(table_name: str) -> str:
    """SQL インジェクション対策として、テーブル名は英数とアンダースコアのみに制限。"""
    if not re.match(r"^[A-Za-z0-9_]+$", table_name):
        raise ValueError(f"不正なテーブル名です: {table_name!r}")
    return table_name


def list_loto_tables() -> pd.DataFrame:
    """nf_loto% で始まるテーブル一覧を返す。"""
    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
              AND tablename LIKE 'nf_loto%%'
            ORDER BY tablename
            """,
            conn,
        )
    return df


def list_loto_values(table_name: str) -> pd.DataFrame:
    """指定テーブルの loto 値一覧を返す。"""
    table_name = _validate_table_name(table_name)
    query = f"""SELECT DISTINCT loto FROM {table_name} ORDER BY loto"""
    with get_connection() as conn:
        df = pd.read_sql(query, conn)
    return df


def list_unique_ids(table_name: str, loto: str) -> pd.DataFrame:
    """指定テーブル + loto の unique_id 一覧を返す。"""
    table_name = _validate_table_name(table_name)
    query = f"""
        SELECT DISTINCT unique_id
        FROM {table_name}
        WHERE loto = %s
        ORDER BY unique_id
    """
    with get_connection() as conn:
        df = pd.read_sql(query, conn, params=[loto])
    return df


def load_panel_by_loto(
    table_name: str,
    loto: str,
    unique_ids: Sequence[str],
) -> pd.DataFrame:
    """nf_loto テーブルから、指定された loto × unique_ids のパネルデータを取得。

    NeuralForecast の期待するスキーマ:
        - unique_id
        - ds
        - y
        - その他の列:
            - hist_*  : 過去のみ既知の外生
            - stat_*  : 静的外生
            - futr_*  : 未来まで既知の外生
    """
    table_name = _validate_table_name(table_name)
    if not unique_ids:
        raise ValueError("unique_ids が空です。最低 1 件指定してください。")

    # IN 句をプレースホルダで安全に構築
    placeholders = ",".join(["%s"] * len(unique_ids))
    query = f"""
        SELECT *
        FROM {table_name}
        WHERE loto = %s
          AND unique_id IN ({placeholders})
        ORDER BY unique_id, ds
    """
    params = [loto, *list(unique_ids)]
    with get_connection() as conn:
        df = pd.read_sql(query, conn, params=params)

    # NeuralForecast の標準カラム名が揃っているか軽くチェック
    required_cols = {"unique_id", "ds", "y"}
    missing = required_cols.difference(df.columns)
    if missing:
        raise ValueError(f"必要なカラムが不足しています: {missing}")

    return df
