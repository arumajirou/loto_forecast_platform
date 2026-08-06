from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from loto.orchestration.pipeline_downstream_preflight import DownstreamCommitConflict
from loto.orchestration.pipeline_downstream_types import canonical_json_bytes


def atomic_write_json(path: Path, payload: Any) -> None:
    if path.is_symlink():
        raise DownstreamCommitConflict(f"output artifact is a symlink: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
        default=str,
    )
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def json_equal(left: Any, right: Any) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def reject_symlink_components(path: Path, *, label: str) -> None:
    absolute = absolute_path(path)
    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and candidate.is_symlink():
            raise DownstreamCommitConflict(
                f"{label} must not contain a symlink component: {candidate}"
            )


def file_uri_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise DownstreamCommitConflict(
            f"artifact store returned a non-file URI: {uri}"
        )
    return Path(unquote(parsed.path))


def platform_local_path(value: str) -> Path | None:
    if value.startswith("sqlite:///"):
        return Path(value.removeprefix("sqlite:///"))
    if "://" not in value:
        return Path(value)
    return None


@dataclass(frozen=True)
class DownstreamCommitConfig:
    registry_path: Path
    platform_registry_url: str
    artifact_store_root: Path
    events_path: Path
    mlflow_tracking_uri: str
    mlflow_experiment_name: str
