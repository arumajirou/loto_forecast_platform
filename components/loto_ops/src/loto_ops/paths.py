from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    ops_project: Path
    loto_life_project: Path
    loto_forecast_project: Path
    zip_output_dir: Path

    @property
    def runs_dir(self) -> Path:
        return self.ops_project / "runs"

    @property
    def artifacts_dir(self) -> Path:
        return self.ops_project / "artifacts"

    @property
    def reports_dir(self) -> Path:
        return self.artifacts_dir / "reports"

    @property
    def datasets_dir(self) -> Path:
        return self.artifacts_dir / "datasets"

    @property
    def zips_dir(self) -> Path:
        return self.artifacts_dir / "zips"

    @property
    def sqlite_path(self) -> Path:
        return self.loto_life_project / "data" / "loto_forecast_dataset.sqlite"

    @property
    def postgres_load_dir(self) -> Path:
        return self.loto_life_project / "data" / "postgres_load"


def new_run_id(prefix: str = "loto_ops") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
