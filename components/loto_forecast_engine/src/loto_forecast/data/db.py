from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from loto_forecast.config.settings import settings

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(value: str, *, label: str) -> str:
    raw = str(value).strip()
    if not _IDENT.fullmatch(raw):
        raise ValueError(f"invalid {label}: {value!r}")
    return raw


def make_engine(url: str | None = None) -> Engine:
    if url is None:
        password = quote_plus(settings.db_password)
        user = quote_plus(settings.db_user)
        url = (
            f"postgresql+psycopg2://{user}:{password}@"
            f"{settings.db_host}:{settings.db_port}/{settings.db_name}"
        )
    return create_engine(url, pool_pre_ping=True)


def table_columns(engine: Engine, schema: str, table: str) -> list[tuple[str, str]]:
    schema = _identifier(schema, label="schema")
    table = _identifier(table, label="table")
    query = text(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
        """
    )
    with engine.connect() as conn:
        return [(str(row[0]), str(row[1])) for row in conn.execute(query, {"schema": schema, "table": table}).fetchall()]


def table_exists(engine: Engine, schema: str, table: str) -> bool:
    schema = _identifier(schema, label="schema")
    table = _identifier(table, label="table")
    query = text(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = :schema AND table_name = :table
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        return conn.execute(query, {"schema": schema, "table": table}).first() is not None


def read_timeseries(
    engine: Engine,
    schema: str,
    table: str,
    *,
    where_sql: str | None = None,
    params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    schema = _identifier(schema, label="schema")
    table = _identifier(table, label="table")
    sql = f'SELECT * FROM "{schema}"."{table}"'
    if where_sql and str(where_sql).strip():
        # This argument is retained for compatibility with the original project.
        # Callers must provide trusted application SQL, never raw browser input.
        sql += f" WHERE {str(where_sql).strip()}"
    frame = pd.read_sql(text(sql), engine, params=params)
    if "ds" in frame.columns:
        frame["ds"] = pd.to_datetime(frame["ds"], errors="coerce")
    return frame


def read_query(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    frame = pd.read_sql(text(sql), engine, params=params)
    if "ds" in frame.columns:
        frame["ds"] = pd.to_datetime(frame["ds"], errors="coerce")
    return frame


def execute_sql(engine: Engine, sql: str) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


def execute_sql_file(engine: Engine, path: str | Path) -> None:
    sql_path = Path(path)
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")
    execute_sql(engine, sql_path.read_text(encoding="utf-8"))
