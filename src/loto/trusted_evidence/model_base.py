"""Shared strict model and verification-material contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import material_inventory_sha256

SCHEMA_VERSION = "1.0.0"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )


def require_timezone(value: datetime, label: str) -> datetime:
    if value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


class VerificationMaterial(StrictModel):
    material_id: str = Field(min_length=1, max_length=256)
    relative_path: str = Field(min_length=1, max_length=4096)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=256)
    role: str = Field(min_length=1, max_length=256)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or value.startswith(("/", "\\")):
            raise ValueError("verification material path must be relative")
        if "\\" in value or ":" in value:
            raise ValueError("verification material path must use POSIX syntax")
        if any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("verification material path contains an unsafe component")
        return value


class MaterialBoundEvidence(StrictModel):
    verification_materials: list[VerificationMaterial] = Field(default_factory=list)
    verification_material_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_material_inventory(self) -> MaterialBoundEvidence:
        paths = [item.relative_path for item in self.verification_materials]
        if len(paths) != len(set(paths)):
            raise ValueError("verification material paths must be unique")
        if len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("verification material paths must not collide by case")
        if not self.verification_materials:
            if self.verification_material_sha256 is not None:
                raise ValueError("empty material inventory must not have a digest")
            return self
        expected = material_inventory_sha256(
            [item.model_dump(mode="json") for item in self.verification_materials]
        )
        if self.verification_material_sha256 != expected:
            raise ValueError("verification material inventory SHA-256 mismatch")
        return self
