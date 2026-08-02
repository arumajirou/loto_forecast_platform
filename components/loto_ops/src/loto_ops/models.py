from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

Status = Literal["pending", "running", "success", "warning", "failed", "skipped"]


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class StageResult:
    name: str
    status: Status
    started_at: str | None = None
    finished_at: str | None = None
    rows: int | None = None
    columns: int | None = None
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactInfo:
    kind: str
    path: str
    size_bytes: int | None = None
    sha256: str | None = None


@dataclass
class TableProfile:
    schema: str
    table: str
    rows: int | None = None
    columns: int | None = None
    min_ds: str | None = None
    max_ds: str | None = None
    null_summary: dict[str, float] = field(default_factory=dict)
    duplicate_count: int | None = None


@dataclass
class RunManifest:
    run_id: str
    started_at: str
    finished_at: str | None = None
    status: Status = "running"
    stages: list[StageResult] = field(default_factory=list)
    tables: list[TableProfile] = field(default_factory=list)
    artifacts: list[ArtifactInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: Path) -> None:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
