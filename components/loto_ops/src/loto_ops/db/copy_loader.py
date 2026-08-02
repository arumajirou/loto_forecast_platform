from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

import pandas as pd

from loto_ops.config import AppSettings


class CopyLoader:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.sqlite_path = settings.paths.sqlite_path
        self.out_dir = settings.paths.postgres_load_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def quote_ident(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    @staticmethod
    def pg_type(col: str) -> str:
        if col == "ds":
            return "DATE"
        if col in {"exec_ts", "updated_ts"}:
            return "TIMESTAMP WITHOUT TIME ZONE"
        if col in {"y", "proc_seconds"} or col.startswith("hist_"):
            return "DOUBLE PRECISION"
        return "TEXT"

    def export_sqlite_to_csv_and_sql(self) -> Path:
        if not self.sqlite_path.exists():
            raise FileNotFoundError(f"SQLite not found: {self.sqlite_path}")

        tables = [
            ("dataset_loto_y_ts", "loto_y_ts", self.out_dir / "loto_y_ts.csv"),
            ("dataset_loto_hist_feat", "loto_hist_feat", self.out_dir / "loto_hist_feat.csv"),
        ]
        sql_lines = [
            "CREATE SCHEMA IF NOT EXISTS dataset;",
            "DROP TABLE IF EXISTS dataset.loto_y_ts_staging CASCADE;",
            "DROP TABLE IF EXISTS dataset.loto_hist_feat_staging CASCADE;",
        ]

        with sqlite3.connect(self.sqlite_path) as conn:
            for sqlite_table, pg_table, csv_path in tables:
                df = pd.read_sql_query(f"SELECT * FROM {sqlite_table}", conn)
                if df.empty:
                    raise ValueError(f"{sqlite_table} is empty")
                staging_table = f"{pg_table}_staging"
                df.to_csv(csv_path, index=False, encoding="utf-8")
                cols = list(df.columns)
                col_defs = ",\n  ".join(f"{self.quote_ident(c)} {self.pg_type(c)}" for c in cols)
                col_names = ", ".join(self.quote_ident(c) for c in cols)
                sql_lines.append(
                    f"CREATE TABLE dataset.{self.quote_ident(staging_table)} (\n  {col_defs}\n);"
                )
                sql_lines.append(
                    f"\\copy dataset.{self.quote_ident(staging_table)} ({col_names}) "
                    f"FROM '{csv_path}' WITH (FORMAT csv, HEADER true);"
                )

        sql_lines += [
            "DROP TABLE IF EXISTS dataset.loto_y_ts CASCADE;",
            "ALTER TABLE dataset.loto_y_ts_staging RENAME TO loto_y_ts;",
            "DROP TABLE IF EXISTS dataset.loto_hist_feat CASCADE;",
            "ALTER TABLE dataset.loto_hist_feat_staging RENAME TO loto_hist_feat;",
            "CREATE INDEX IF NOT EXISTS idx_loto_y_ts_key ON dataset.loto_y_ts (loto, unique_id, ts_type, ds);",
            "CREATE INDEX IF NOT EXISTS idx_loto_hist_feat_key ON dataset.loto_hist_feat (loto, unique_id, ds);",
            "ANALYZE dataset.loto_y_ts;",
            "ANALYZE dataset.loto_hist_feat;",
        ]
        load_sql = self.out_dir / "load_dataset.sql"
        load_sql.write_text("\n\n".join(sql_lines) + "\n", encoding="utf-8")
        return load_sql

    def run_psql_copy(self, load_sql: Path | None = None) -> None:
        db = self.settings.db
        target_sql = load_sql or (self.out_dir / "load_dataset.sql")
        env = os.environ.copy()
        env["PGPASSWORD"] = db.password
        subprocess.run([*db.psql_base_args, "-f", str(target_sql)], env=env, check=True)
