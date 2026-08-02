from __future__ import annotations

import os
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from loto_ops.config import AppSettings
from loto_ops.db.copy_loader import CopyLoader
from loto_ops.progress import make_bar


@dataclass(frozen=True)
class CopyTask:
    table: str
    csv_path: Path
    columns: list[str]
    rows: int


class FastCopyLoader(CopyLoader):
    """COPY-based PostgreSQL loader with partitioned CSV and parallel psql clients."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.fast_cfg = settings.raw.get("fast_mode", {})
        self.partition_dir = self.out_dir / "partitioned"
        self.partition_dir.mkdir(parents=True, exist_ok=True)

    def export_partitioned_sqlite_to_csv_and_sql(
        self, *, partition_by: str = "loto"
    ) -> dict[str, object]:
        started = time.perf_counter()
        if not self.sqlite_path.exists():
            raise FileNotFoundError(f"SQLite not found: {self.sqlite_path}")

        yts = self._read_sqlite_table("dataset_loto_y_ts")
        hist = self._read_sqlite_table("dataset_loto_hist_feat")
        if yts.empty or hist.empty:
            raise ValueError("SQLite dataset tables must be non-empty before COPY load")

        yts_tasks = self._write_partitions(yts, table="loto_y_ts", partition_by=partition_by)
        hist_tasks = self._write_partitions(hist, table="loto_hist_feat", partition_by=partition_by)
        prepare_sql = self._write_prepare_sql(yts, hist)
        promote_sql = self._write_promote_sql()
        manifest = {
            "prepare_sql": str(prepare_sql),
            "promote_sql": str(promote_sql),
            "tasks": [
                task.__dict__ | {"csv_path": str(task.csv_path)}
                for task in [*yts_tasks, *hist_tasks]
            ],
            "rows": {"loto_y_ts": len(yts), "loto_hist_feat": len(hist)},
            "seconds": round(time.perf_counter() - started, 3),
        }
        (self.out_dir / "parallel_copy_manifest.json").write_text(
            __import__("json").dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    def run_parallel_copy(
        self, *, jobs: int | None = None, show_progress: bool = True
    ) -> dict[str, object]:
        jobs = int(jobs or self.fast_cfg.get("copy_jobs", 6))
        manifest = self.export_partitioned_sqlite_to_csv_and_sql()
        tasks = [
            CopyTask(
                table=str(item["table"]),
                csv_path=Path(str(item["csv_path"])),
                columns=list(item["columns"]),
                rows=int(item["rows"]),
            )
            for item in manifest["tasks"]
        ]
        self._run_psql_file(Path(str(manifest["prepare_sql"])))
        started = time.perf_counter()
        results: list[dict[str, object]] = []
        total_rows = sum(task.rows for task in tasks) or 1
        copied_rows = 0
        completed_tasks = 0
        if show_progress:
            print(
                f"[progress] {make_bar(0)}   0.00% | COPY start tasks={len(tasks)} rows={total_rows}",
                flush=True,
            )
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            future_map = {pool.submit(self._copy_task, task): task for task in tasks}
            for fut in as_completed(future_map):
                task = future_map[fut]
                try:
                    fut.result()
                    completed_tasks += 1
                    copied_rows += task.rows
                    results.append(
                        {
                            "table": task.table,
                            "csv": str(task.csv_path),
                            "rows": task.rows,
                            "status": "success",
                        }
                    )
                    if show_progress:
                        pct = 100.0 * copied_rows / total_rows
                        print(
                            f"[progress] {make_bar(pct)} {pct:6.2f}% | "
                            f"COPY {completed_tasks}/{len(tasks)} rows={copied_rows}/{total_rows} "
                            f"last={task.table}:{task.csv_path.name}",
                            flush=True,
                        )
                except Exception as exc:
                    results.append(
                        {
                            "table": task.table,
                            "csv": str(task.csv_path),
                            "rows": task.rows,
                            "status": "failed",
                            "error": str(exc),
                        }
                    )
                    if show_progress:
                        pct = 100.0 * copied_rows / total_rows
                        print(
                            f"[progress] {make_bar(pct)} {pct:6.2f}% | COPY failed {task.csv_path.name}: {exc}",
                            flush=True,
                        )
                    raise
        if show_progress:
            print(
                f"[progress] {make_bar(100)} 100.00% | COPY complete; promoting tables", flush=True
            )
        self._run_psql_file(Path(str(manifest["promote_sql"])))
        return {"jobs": jobs, "tasks": results, "seconds": round(time.perf_counter() - started, 3)}

    def _read_sqlite_table(self, table: str) -> pd.DataFrame:
        with sqlite3.connect(self.sqlite_path) as conn:
            return pd.read_sql_query(f"SELECT * FROM {table}", conn)

    def _write_partitions(
        self, df: pd.DataFrame, *, table: str, partition_by: str
    ) -> list[CopyTask]:
        tasks: list[CopyTask] = []
        columns = list(df.columns)
        if partition_by not in df.columns:
            csv_path = self.partition_dir / f"{table}.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8")
            return [CopyTask(table=table, csv_path=csv_path, columns=columns, rows=len(df))]
        for key, part in df.groupby(partition_by, sort=True, dropna=False):
            safe_key = str(key).replace("/", "_").replace(" ", "_")
            csv_path = self.partition_dir / f"{table}_{safe_key}.csv"
            part.to_csv(csv_path, index=False, encoding="utf-8")
            tasks.append(CopyTask(table=table, csv_path=csv_path, columns=columns, rows=len(part)))
        return tasks

    def _write_prepare_sql(self, yts: pd.DataFrame, hist: pd.DataFrame) -> Path:
        unlogged = bool(self.fast_cfg.get("use_unlogged_staging", True))
        table_kind = "UNLOGGED TABLE" if unlogged else "TABLE"
        tuning = self.fast_cfg.get("postgres_session_tuning", {})
        lines: list[str] = ["CREATE SCHEMA IF NOT EXISTS dataset;"]
        for key, value in tuning.items():
            lines.append(f"SET {key} = '{value}';")
        lines += [
            "DROP TABLE IF EXISTS dataset.loto_y_ts_staging CASCADE;",
            "DROP TABLE IF EXISTS dataset.loto_hist_feat_staging CASCADE;",
            self._create_table_sql(yts, f"CREATE {table_kind} dataset.loto_y_ts_staging"),
            self._create_table_sql(hist, f"CREATE {table_kind} dataset.loto_hist_feat_staging"),
        ]
        path = self.out_dir / "00_prepare_parallel_copy.sql"
        path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _write_promote_sql(self) -> Path:
        lines = [
            "DROP TABLE IF EXISTS dataset.loto_y_ts CASCADE;",
            "ALTER TABLE dataset.loto_y_ts_staging RENAME TO loto_y_ts;",
            "DROP TABLE IF EXISTS dataset.loto_hist_feat CASCADE;",
            "ALTER TABLE dataset.loto_hist_feat_staging RENAME TO loto_hist_feat;",
            "CREATE INDEX IF NOT EXISTS idx_loto_y_ts_key ON dataset.loto_y_ts (loto, unique_id, ts_type, ds);",
            "CREATE INDEX IF NOT EXISTS idx_loto_hist_feat_key ON dataset.loto_hist_feat (loto, unique_id, ds);",
            "ANALYZE dataset.loto_y_ts;",
            "ANALYZE dataset.loto_hist_feat;",
        ]
        path = self.out_dir / "99_promote_parallel_copy.sql"
        path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _create_table_sql(self, df: pd.DataFrame, prefix: str) -> str:
        col_defs = ",\n  ".join(f"{self.quote_ident(c)} {self.pg_type(c)}" for c in df.columns)
        return f"{prefix} (\n  {col_defs}\n);"

    def _copy_task(self, task: CopyTask) -> None:
        col_names = ", ".join(self.quote_ident(c) for c in task.columns)
        sql = (
            f"\\copy dataset.{self.quote_ident(task.table + '_staging')} ({col_names}) "
            f"FROM '{task.csv_path}' WITH (FORMAT csv, HEADER true)"
        )
        db = self.settings.db
        env = os.environ.copy()
        env["PGPASSWORD"] = db.password
        subprocess.run([*db.psql_base_args, "-c", sql], env=env, check=True)

    def _run_psql_file(self, path: Path) -> None:
        db = self.settings.db
        env = os.environ.copy()
        env["PGPASSWORD"] = db.password
        subprocess.run([*db.psql_base_args, "-f", str(path)], env=env, check=True)
