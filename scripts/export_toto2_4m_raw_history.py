from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.toto2_campaign.raw_history_export import (  # noqa: E402
    FORMAL_GAMES,
    SOURCE_SCHEMA,
    SOURCE_TABLE,
    SOURCE_TS_TYPE,
    build_exports,
    write_export_bundle,
)

QUERY_TEXT = """SELECT
    LOWER(loto)::text AS game_id,
    ds::date AS ds,
    unique_id::text AS unique_id,
    y::double precision AS y
FROM dataset.loto_y_ts_unified
WHERE LOWER(loto) IN ('numbers3', 'numbers4', 'miniloto', 'loto6', 'loto7')
  AND LOWER(ts_type) = 'raw'
ORDER BY LOWER(loto), ds, unique_id;
"""

SCHEMA_QUERY = """SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = :schema_name
  AND table_name = :table_name
ORDER BY ordinal_position
"""

SNAPSHOT_QUERY = """SELECT
    current_database() AS database_name,
    current_user AS database_user,
    current_setting('server_version') AS server_version,
    current_setting('transaction_isolation') AS transaction_isolation,
    current_setting('transaction_read_only')::boolean AS transaction_read_only,
    txid_current_snapshot()::text AS transaction_snapshot
"""


def _database_url():
    try:
        from sqlalchemy import URL
    except ImportError as exc:
        raise RuntimeError("SQLAlchemy is required; run with the postgres extra") from exc
    required = ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError(f"database environment variables are missing: {missing}")
    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
    )


def _validate_schema(schema: pd.DataFrame) -> list[dict[str, str]]:
    required = {"loto", "ds", "unique_id", "ts_type", "y"}
    actual = set(schema["column_name"].astype(str))
    missing = sorted(required - actual)
    if missing:
        raise ValueError(f"source table is missing required columns: {missing}")
    rows = [
        {"column_name": str(row.column_name), "data_type": str(row.data_type)}
        for row in schema.itertuples(index=False)
        if str(row.column_name) in required
    ]
    return rows


def export(output_root: Path) -> dict[str, Any]:
    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:
        raise RuntimeError("SQLAlchemy is required; run with the postgres extra") from exc
    engine = create_engine(_database_url(), pool_pre_ping=True)
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        )
        try:
            connection.exec_driver_sql("SET LOCAL statement_timeout = '10min'")
            schema = pd.read_sql_query(
                text(SCHEMA_QUERY),
                connection,
                params={"schema_name": SOURCE_SCHEMA, "table_name": SOURCE_TABLE},
            )
            schema_evidence = _validate_schema(schema)
            snapshot_row = connection.execute(text(SNAPSHOT_QUERY)).mappings().one()
            source = pd.read_sql_query(text(QUERY_TEXT), connection)
        finally:
            connection.exec_driver_sql("ROLLBACK")

    database_snapshot = {
        "schema_version": 1,
        "source_schema": SOURCE_SCHEMA,
        "source_table": SOURCE_TABLE,
        "source_ts_type": SOURCE_TS_TYPE,
        "formal_games": list(FORMAL_GAMES),
        "transaction_isolation": str(snapshot_row["transaction_isolation"]).lower(),
        "transaction_read_only": bool(snapshot_row["transaction_read_only"]),
        "transaction_snapshot": str(snapshot_row["transaction_snapshot"]),
        "database_name": str(snapshot_row["database_name"]),
        "database_user": str(snapshot_row["database_user"]),
        "server_version": str(snapshot_row["server_version"]),
        "required_columns": schema_evidence,
        "password_recorded": False,
        "raw_data_modified": False,
    }
    if database_snapshot["transaction_isolation"] != "repeatable read":
        raise RuntimeError("database did not enter repeatable-read isolation")
    if database_snapshot["transaction_read_only"] is not True:
        raise RuntimeError("database transaction was not read-only")
    exports = build_exports(source)
    return write_export_bundle(
        exports,
        output_root=output_root,
        database_snapshot=database_snapshot,
        query_text=QUERY_TEXT,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export immutable five-game raw history for Toto 2.0 certification"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = export(args.output_root)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"TOTO2_RAW_HISTORY_EXPORT=FAILED\nERROR={type(exc).__name__}: {exc}")
        return 2
    print("TOTO2_RAW_HISTORY_EXPORT=PASS")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"GAME_COUNT={len(manifest['games'])}")
    print("RAW_DATA_MODIFIED=false")
    print("VERIFICATION_REQUIRED=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
