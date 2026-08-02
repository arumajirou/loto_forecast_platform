from __future__ import annotations

from sqlalchemy import inspect, text

from loto_ops.config import AppSettings
from loto_ops.db.connection import make_engine
from loto_ops.models import TableProfile

IMPORTANT_TABLES = [
    ("dataset", "loto_y_ts"),
    ("dataset", "loto_hist_feat"),
    ("dataset", "loto_y_ts_unified"),
    ("exog", "loto_y_ts_exog"),
    ("meta", "model_run"),
]


def profile_table(settings: AppSettings, schema: str, table: str) -> TableProfile:
    engine = make_engine(settings.db)
    try:
        insp = inspect(engine)
        if not insp.has_table(table, schema=schema):
            return TableProfile(schema=schema, table=table, rows=None, columns=None)
        cols = [c["name"] for c in insp.get_columns(table, schema=schema)]
        with engine.begin() as conn:
            rows = int(
                conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')).scalar_one()
            )
            min_ds = max_ds = None
            if "ds" in cols:
                r = conn.execute(
                    text(f'SELECT MIN(ds)::text, MAX(ds)::text FROM "{schema}"."{table}"')
                ).one()
                min_ds, max_ds = r[0], r[1]
        return TableProfile(
            schema=schema, table=table, rows=rows, columns=len(cols), min_ds=min_ds, max_ds=max_ds
        )
    finally:
        engine.dispose()


def profile_important_tables(settings: AppSettings) -> list[TableProfile]:
    return [profile_table(settings, s, t) for s, t in IMPORTANT_TABLES]
