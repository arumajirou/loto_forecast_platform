from __future__ import annotations

import pandas as pd

from .db_service import query_df


def list_tables() -> pd.DataFrame:
    return query_df(
        """
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('dataset','exog','meta','log','public')
ORDER BY table_schema, table_name
"""
    )


def table_count(schema: str, table: str) -> int | None:
    df = query_df(f'SELECT COUNT(*) AS rows FROM "{schema}"."{table}"')
    return int(df.iloc[0]["rows"])


def table_columns(schema: str, table: str) -> pd.DataFrame:
    return query_df(
        """
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = :schema AND table_name = :table
ORDER BY ordinal_position
""",
        {"schema": schema, "table": table},
    )


def preview_table(schema: str, table: str, limit: int = 100) -> pd.DataFrame:
    limit = max(1, min(int(limit), 5000))
    return query_df(f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}')
