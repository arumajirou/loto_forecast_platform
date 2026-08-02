from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PipelineManifest:
    """Run manifest tracking artifacts, stages, and errors."""

    def __init__(self, run_id: str, status: str = "running") -> None:
        self.run_id = run_id
        self.status = status
        self.stages: dict[str, dict[str, Any]] = {}
        self.artifacts: list[dict[str, str]] = []
        self.errors: list[dict[str, str]] = []
        self.last_successful_stage: str | None = None

    def add_stage(self, stage_name: str, duration: float) -> None:
        self.stages[stage_name] = {"duration_seconds": duration}

    def add_artifact(self, artifact_name: str, artifact_type: str) -> None:
        self.artifacts.append({"name": artifact_name, "type": artifact_type})

    def add_error(self, stage_name: str, error_message: str) -> None:
        self.errors.append({"stage": stage_name, "message": error_message})

    def set_status(self, status: str) -> None:
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": self.status,
            "stages": self.stages,
            "artifacts": self.artifacts,
            "errors": self.errors,
            "last_successful_stage": self.last_successful_stage,
        }

    def write(self, run_dir: Path) -> Path:
        manifest_path = run_dir / "run_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return manifest_path
