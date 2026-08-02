from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from loto_ops.config import DbSettings


def make_engine(db: DbSettings) -> Engine:
    return create_engine(db.sqlalchemy_url, pool_pre_ping=True)


def check_connection(db: DbSettings) -> dict[str, str]:
    engine = make_engine(db)
    try:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT current_database(), current_user, now()::text")).one()
            return {"database": row[0], "user": row[1], "checked_at": row[2]}
    finally:
        engine.dispose()
