from __future__ import annotations

import os
import subprocess

from sqlalchemy import text

from loto_ops.config import AppSettings
from loto_ops.db.connection import make_engine


class DbAdmin:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.db = settings.db

    def check_connection(self) -> dict[str, str]:
        from .connection import check_connection

        return check_connection(self.db)

    def init_schema(self) -> None:
        """Run existing loto_forecast_project db-init safely."""
        project = self.settings.paths.loto_forecast_project
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(project / "src"),
                "DB_HOST": self.db.host,
                "DB_PORT": str(self.db.port),
                "DB_USER": self.db.user,
                "DB_PASSWORD": self.db.password,
                "DB_NAME": self.db.database,
                "LOTO_ALLOW_DB_INIT": "1",
            }
        )
        subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "python",
                "-m",
                "loto_forecast.cli",
                "db-init",
                "--yes-i-understand-db-init-may-write",
            ],
            cwd=project,
            env=env,
            check=True,
        )

    def reset_pipeline_tables(self, confirm_reset: bool = False) -> None:
        if not confirm_reset:
            raise ValueError("reset_pipeline_tables requires confirm_reset=True")
        engine = make_engine(self.db)
        try:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS dataset.loto_y_ts_unified CASCADE"))
                conn.execute(text("DROP TABLE IF EXISTS dataset.loto_y_ts CASCADE"))
                conn.execute(text("DROP TABLE IF EXISTS dataset.loto_hist_feat CASCADE"))
                conn.execute(text("DROP SCHEMA IF EXISTS exog CASCADE"))
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS exog"))
        finally:
            engine.dispose()

    def create_loto_database_if_missing(self) -> None:
        env = os.environ.copy()
        env["PGPASSWORD"] = self.db.password
        sql = f"""
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{self.db.user}') THEN
    CREATE ROLE {self.db.user} LOGIN PASSWORD '{self.db.password}';
  END IF;
END $$;
ALTER ROLE {self.db.user} WITH CREATEDB;
SELECT 'CREATE DATABASE {self.db.database} WITH OWNER = {self.db.user} ENCODING = ''UTF8'' TEMPLATE = template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '{self.db.database}')\\gexec
"""
        subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-d", "postgres", "-X", "-P", "pager=off"],
            input=sql,
            text=True,
            check=True,
        )

    def list_tables(
        self, schemas: tuple[str, ...] = ("dataset", "exog", "meta", "log", "public")
    ) -> list[dict[str, str]]:
        engine = make_engine(self.db)
        try:
            with engine.begin() as conn:
                rows = (
                    conn.execute(
                        text(
                            """
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = ANY(:schemas)
ORDER BY table_schema, table_name
"""
                        ),
                        {"schemas": list(schemas)},
                    )
                    .mappings()
                    .all()
                )
                return [dict(r) for r in rows]
        finally:
            engine.dispose()
