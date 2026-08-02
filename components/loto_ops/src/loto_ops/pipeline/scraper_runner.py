from __future__ import annotations

import os
import shutil
import subprocess

from loto_ops.config import AppSettings


def _uv_bin(env: dict[str, str]) -> str:
    return env.get("UV_BIN") or shutil.which("uv") or "/home/az/.local/bin/uv"


class ScraperRunner:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def run(self, games: str = "all", force: bool = True) -> None:
        project = self.settings.paths.loto_life_project
        if not project.exists():
            raise FileNotFoundError(
                f"loto_life_feature_pipeline project not found: {project}. "
                "Set LOTO_LIFE_PROJECT or update configs/loto_ops.yaml paths.loto_life_project. "
                "If this is a scheduled run on Kubuntu/WSL startup, run `loto-ops path-status` first."
            )
        if not (project / "pyproject.toml").exists():
            raise FileNotFoundError(
                f"loto_life_feature_pipeline looks incomplete: {project} (pyproject.toml not found)."
            )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project / "src")
        cmd = [
            _uv_bin(env),
            "run",
            "python",
            "-m",
            "loto_life_features.cli",
            "run-all",
            "--config",
            "configs/lotteries.json",
            "--games",
            games,
            "--raw-dir",
            "data/raw",
            "--interim-dir",
            "data/interim",
            "--processed-dir",
            "data/processed",
        ]
        if force:
            cmd.append("--force")
        subprocess.run(cmd, cwd=project, env=env, check=True)
