from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .paths import ProjectPaths

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "loto_ops.yaml"

# Cache for loaded settings to avoid repeated file IO
_settings_cache: dict[str, Any] = {}


@dataclass(frozen=True)
class DbSettings:
    host: str
    port: int
    user: str
    password: str
    database: str
    maintenance_database: str = "postgres"

    @property
    def sqlalchemy_url(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def psql_base_args(self) -> list[str]:
        return [
            "psql",
            "-h",
            self.host,
            "-p",
            str(self.port),
            "-U",
            self.user,
            "-d",
            self.database,
            "-X",
            "-P",
            "pager=off",
        ]


@dataclass(frozen=True)
class AppSettings:
    paths: ProjectPaths
    db: DbSettings
    pipeline: dict[str, Any]
    scheduler: dict[str, Any]
    workflow: dict[str, Any]
    raw: dict[str, Any]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _get_cache_key(path: Path) -> str:
    """Generate cache key based on file path and modification time."""
    stat = path.stat()
    return f"{path}:{stat.st_mtime}:{stat.st_size}"


def _first_existing(candidates: list[Path], fallback: Path) -> Path:
    """Return the first existing candidate, otherwise a deterministic fallback."""
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.expanduser().resolve(strict=False)
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate
    return fallback.expanduser().resolve(strict=False)


def load_settings(config_path: str | Path | None = None) -> AppSettings:
    path = (
        Path(config_path or os.getenv("LOTO_OPS_CONFIG", DEFAULT_CONFIG_PATH))
        .expanduser()
        .resolve(strict=False)
    )
    cache_key = _get_cache_key(path)

    # Return cached settings if file hasn't changed
    if cache_key in _settings_cache:
        return _settings_cache[cache_key]

    raw = _read_yaml(path)
    raw_paths = raw.get("paths", {})
    config_project_root = path.parent.parent

    configured_ops = Path(str(raw_paths.get("ops_project", config_project_root)))
    ops_env = os.getenv("LOTO_OPS_PROJECT")
    ops_project = (
        Path(ops_env).expanduser().resolve(strict=False)
        if ops_env
        else _first_existing(
            [configured_ops, config_project_root, PROJECT_ROOT],
            config_project_root,
        )
    )

    life_env = os.getenv("LOTO_LIFE_PROJECT")
    configured_life = Path(
        str(raw_paths.get("loto_life_project", ops_project.parent / "loto_life_feature_pipeline"))
    )
    loto_life_project = (
        Path(life_env).expanduser().resolve(strict=False)
        if life_env
        else _first_existing(
            [
                configured_life,
                ops_project.parent / "loto_life_feature_pipeline",
                Path("/mnt/e/env/ts/loto_life_feature_pipeline"),
                Path("/mnt/e/env/ts/codex/loto_life_feature_pipeline"),
                Path("/mnt/e/env/fc/loto_life_feature_pipeline"),
                Path("/mnt/e/env/fc/old/loto_life_feature_pipeline"),
            ],
            configured_life,
        )
    )

    forecast_env = os.getenv("LOTO_FORECAST_PROJECT")
    configured_forecast = Path(
        str(raw_paths.get("loto_forecast_project", ops_project.parent / "loto_forecast_project"))
    )
    loto_forecast_project = (
        Path(forecast_env).expanduser().resolve(strict=False)
        if forecast_env
        else _first_existing(
            [
                configured_forecast,
                ops_project.parent / "loto_forecast_project",
                ops_project.parent / "loto_neuralforecast_pipeline",
                Path("/mnt/e/env/ts/loto_forecast_project"),
                Path("/mnt/e/env/ts/loto_neuralforecast_pipeline"),
                Path("/mnt/e/env/fc/loto_forecast_project"),
            ],
            configured_forecast,
        )
    )

    zip_env = os.getenv("LOTO_ZIP_OUTPUT_DIR")
    configured_zip = Path(str(raw_paths.get("zip_output_dir", ops_project / "artifacts" / "zips")))
    zip_output_dir = (
        Path(zip_env).expanduser().resolve(strict=False)
        if zip_env
        else _first_existing(
            [configured_zip, ops_project.parent / "zips", ops_project / "artifacts" / "zips"],
            ops_project / "artifacts" / "zips",
        )
    )

    paths = ProjectPaths(
        ops_project=ops_project,
        loto_life_project=loto_life_project,
        loto_forecast_project=loto_forecast_project,
        zip_output_dir=zip_output_dir,
    )

    raw_db = raw.get("db", {})
    db = DbSettings(
        host=os.getenv("DB_HOST", str(raw_db.get("host", "127.0.0.1"))),
        port=int(os.getenv("DB_PORT", raw_db.get("port", 5432))),
        user=os.getenv("DB_USER", str(raw_db.get("user", "loto"))),
        password=os.getenv("DB_PASSWORD", str(raw_db.get("password", "CHANGE_ME"))),
        database=os.getenv("DB_NAME", str(raw_db.get("database", "loto"))),
        maintenance_database=str(raw_db.get("maintenance_database", "postgres")),
    )
    effective_raw = dict(raw)
    effective_raw["runs_dir"] = str(paths.runs_dir)
    effective_raw["config_path"] = str(path)
    effective_raw["paths"] = {
        "ops_project": str(paths.ops_project),
        "loto_life_project": str(paths.loto_life_project),
        "loto_forecast_project": str(paths.loto_forecast_project),
        "zip_output_dir": str(paths.zip_output_dir),
    }

    settings = AppSettings(
        paths=paths,
        db=db,
        pipeline=raw.get("pipeline", {}),
        scheduler=raw.get("scheduler", {}),
        workflow=raw.get("workflow", {}),
        raw=effective_raw,
    )

    # Cache the settings object
    _settings_cache[cache_key] = settings
    return settings
