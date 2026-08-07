from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def hash_mapping(payload: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def hash_dataframe(frame: pd.DataFrame) -> str:
    payload = {
        "columns": list(frame.columns),
        "dtypes": [str(dtype) for dtype in frame.dtypes],
        "data": frame.to_json(
            orient="split",
            date_format="iso",
            date_unit="ns",
            double_precision=15,
        ),
    }
    return hash_mapping(payload)


def hash_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class RunProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    run_id: str = Field(min_length=1)
    created_at_utc: datetime
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit: str = Field(min_length=7)
    model_id: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    seeds: tuple[int, ...]


def build_run_provenance(
    *,
    run_id: str,
    frame: pd.DataFrame,
    config: dict[str, Any],
    code_paths: list[Path],
    git_commit: str,
    model_id: str,
    model_revision: str,
    seeds: tuple[int, ...],
    created_at_utc: datetime | None = None,
) -> RunProvenance:
    created = created_at_utc or datetime.now(UTC)
    if created.tzinfo is None or created.utcoffset() is None:
        raise ValueError("created_at_utc must be timezone-aware")
    if len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise ValueError("provenance must retain at least two unique seeds")
    return RunProvenance(
        run_id=run_id,
        created_at_utc=created.astimezone(UTC),
        data_sha256=hash_dataframe(frame),
        config_sha256=hash_mapping(config),
        code_sha256=hash_files(code_paths),
        git_commit=git_commit,
        model_id=model_id,
        model_revision=model_revision,
        seeds=seeds,
    )


def write_run_provenance(provenance: RunProvenance, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(provenance.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(output)
