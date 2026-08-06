from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import AwareDatetime, BaseModel, field_validator

from .models import STRICT_CONFIG


class ResearchSourceRegistryIndex(BaseModel):
    model_config = STRICT_CONFIG

    schema_version: Literal["1.0.0"]
    generated_at: AwareDatetime
    record_files: tuple[str, ...]

    @field_validator("record_files")
    @classmethod
    def validate_record_files(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate record file")
        for value in values:
            if not value or "\\" in value or value.startswith(("/", "./")):
                raise ValueError("record file must be a safe POSIX relative path")
            path = PurePosixPath(value)
            if any(part in {"", ".", ".."} for part in path.parts):
                raise ValueError("record file must not contain traversal")
        return values
