from __future__ import annotations

import os
import shutil
import subprocess

from loto_ops.config import AppSettings


def _uv_bin(env: dict[str, str]) -> str:
    return env.get("UV_BIN") or shutil.which("uv") or "/home/az/.local/bin/uv"


class UnifiedRunner:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.project = settings.paths.loto_forecast_project

    def run(self) -> None:
        db = self.settings.db
        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONHOME", None)
        env.update(
            {
                "PYTHONPATH": str(self.project / "src"),
                "DB_HOST": db.host,
                "DB_PORT": str(db.port),
                "DB_USER": db.user,
                "DB_PASSWORD": db.password,
                "DB_NAME": db.database,
            }
        )
        subprocess.run(
            [
                _uv_bin(env),
                "run",
                "--no-sync",
                "python",
                "-m",
                "loto_forecast.cli",
                "build-unified-dataset",
                "--host",
                db.host,
                "--port",
                str(db.port),
                "--user",
                db.user,
                "--database",
                db.database,
                "--base-schema",
                "dataset",
                "--base-table",
                "loto_y_ts",
                "--hist-schema",
                "dataset",
                "--hist-table",
                "loto_hist_feat",
                "--exog-schema",
                "exog",
                "--output-schema",
                "dataset",
                "--output-table",
                "loto_y_ts_unified",
                "--postgres-write-mode",
                "to_sql",
                "--show-progress",
            ],
            cwd=self.project,
            env=env,
            check=True,
        )
