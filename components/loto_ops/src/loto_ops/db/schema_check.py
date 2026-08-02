from __future__ import annotations

from sqlalchemy import inspect, text

from loto_ops.config import DbSettings
from loto_ops.db.connection import make_engine


def table_exists(db: DbSettings, schema: str, table: str) -> bool:
    engine = make_engine(db)
    try:
        return inspect(engine).has_table(table, schema=schema)
    finally:
        engine.dispose()


def count_rows(db: DbSettings, schema: str, table: str) -> int | None:
    if not table_exists(db, schema, table):
        return None
    engine = make_engine(db)
    try:
        with engine.begin() as conn:
            return int(
                conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')).scalar_one()
            )
    finally:
        engine.dispose()


def columns(db: DbSettings, schema: str, table: str) -> list[str]:
    engine = make_engine(db)
    try:
        if not inspect(engine).has_table(table, schema=schema):
            return []
        return [c["name"] for c in inspect(engine).get_columns(table, schema=schema)]
    finally:
        engine.dispose()
