from __future__ import annotations

import os
import sqlite3
import subprocess

from loto_ops.config import AppSettings


class DatasetBuilder:
    """Build the loto_forecast-compatible SQLite dataset.

    The upstream loto_life_feature_pipeline script currently writes both SQLite and
    PostgreSQL. Its PostgreSQL write path can fail on large multi-value INSERTs, while
    the SQLite output is still valid. In this ops project PostgreSQL loading is handled
    by CopyLoader via psql \\copy, so this wrapper treats a completed SQLite dataset as
    the success boundary for the build-dataset stage.
    """

    REQUIRED_SQLITE_TABLES = ("dataset_loto_y_ts", "dataset_loto_hist_feat")

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.project = settings.paths.loto_life_project
        self.script = self.project / "scripts" / "create_loto_forecast_dataset.py"
        self.sqlite_path = settings.paths.sqlite_path

    def run(self) -> dict[str, object]:
        if not self.script.exists():
            raise FileNotFoundError(
                f"dataset builder not found: {self.script}. "
                "Create scripts/create_loto_forecast_dataset.py in loto_life_feature_pipeline first."
            )

        env = self._subprocess_env()
        result = subprocess.run(
            ["uv", "run", "python", str(self.script)],
            cwd=self.project,
            env=env,
            check=False,
        )

        profile = self.validate_sqlite_dataset()
        if result.returncode != 0:
            # Known safe case: upstream script failed after writing SQLite, usually in
            # its legacy pandas.to_sql PostgreSQL phase. The next stage, load-postgres,
            # performs the canonical COPY load.
            profile["upstream_returncode"] = result.returncode
            profile["warning"] = (
                "upstream dataset script returned non-zero, but required SQLite tables "
                "exist and are non-empty; continuing because PostgreSQL is loaded by CopyLoader"
            )
        return profile

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "DB_HOST": self.settings.db.host,
                "DB_PORT": str(self.settings.db.port),
                "DB_USER": self.settings.db.user,
                "DB_PASSWORD": self.settings.db.password,
                "DB_NAME": self.settings.db.database,
                "POSTGRES_WRITE_MODE": "copy",
                "LOTO_OPS_MODE": "1",
            }
        )
        # Avoid uv warning when the ops project's .venv is active and we run uv inside
        # loto_life_feature_pipeline.
        env.pop("VIRTUAL_ENV", None)
        env.setdefault("UV_LINK_MODE", "copy")
        return env

    def validate_sqlite_dataset(self) -> dict[str, object]:
        if not self.sqlite_path.exists():
            raise FileNotFoundError(f"SQLite dataset was not created: {self.sqlite_path}")

        rows: dict[str, int] = {}
        with sqlite3.connect(self.sqlite_path) as conn:
            existing = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = [t for t in self.REQUIRED_SQLITE_TABLES if t not in existing]
            if missing:
                raise RuntimeError(f"SQLite dataset is missing required tables: {missing}")
            for table in self.REQUIRED_SQLITE_TABLES:
                count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                if count <= 0:
                    raise RuntimeError(f"SQLite table is empty: {table}")
                rows[table] = count

        return {"sqlite_path": str(self.sqlite_path), "rows": rows}
