from __future__ import annotations

from sqlalchemy import text

from loto_ops.config import DbSettings
from loto_ops.db.connection import make_engine


def promote_staging(
    db: DbSettings, table_pairs: list[tuple[str, str]], schema: str = "dataset"
) -> None:
    engine = make_engine(db)
    try:
        with engine.begin() as conn:
            for staging, production in table_pairs:
                conn.execute(text(f'DROP TABLE IF EXISTS "{schema}"."{production}" CASCADE'))
                conn.execute(text(f'ALTER TABLE "{schema}"."{staging}" RENAME TO "{production}"'))
    finally:
        engine.dispose()
