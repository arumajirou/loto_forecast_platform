from __future__ import annotations

from sqlalchemy import text

from loto_ops.config import DbSettings
from loto_ops.db.connection import make_engine


def list_user_tables(db: DbSettings) -> list[dict[str, object]]:
    engine = make_engine(db)
    try:
        with engine.begin() as conn:
            rows = (
                conn.execute(
                    text(
                        """
SELECT
  table_schema,
  table_name,
  table_type
FROM information_schema.tables
WHERE table_schema NOT LIKE 'pg_%'
  AND table_schema <> 'information_schema'
ORDER BY table_schema, table_name
"""
                    )
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]
    finally:
        engine.dispose()
