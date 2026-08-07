"""Parser identity and input/output hash evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .model_base import SCHEMA_VERSION, SHA256_PATTERN, StrictModel, require_timezone
from .statuses import EvidenceStatus


class ParserEvidence(StrictModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    evidence_id: str = Field(min_length=1, max_length=256)
    status: EvidenceStatus
    parser_name: str | None = Field(default=None, min_length=1, max_length=256)
    parser_version: str | None = Field(default=None, min_length=1, max_length=128)
    parser_code_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_format: str | None = Field(default=None, min_length=1, max_length=128)
    input_raw_bytes_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    output_payload_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    parsed_at_utc: datetime | None = None

    @field_validator("parsed_at_utc")
    @classmethod
    def validate_parsed_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_timezone(value, "parsed_at_utc")

    @model_validator(mode="after")
    def validate_status(self) -> ParserEvidence:
        allowed = {
            EvidenceStatus.NOT_PROVIDED,
            EvidenceStatus.OPERATOR_ASSERTED,
            EvidenceStatus.CORRECTED,
            EvidenceStatus.REVOKED,
        }
        if self.status not in allowed:
            raise ValueError(f"status is not valid for parser evidence: {self.status}")
        fields = (
            self.parser_name,
            self.parser_version,
            self.parser_code_sha256,
            self.source_format,
            self.input_raw_bytes_sha256,
            self.output_payload_sha256,
            self.parsed_at_utc,
        )
        if self.status == EvidenceStatus.NOT_PROVIDED:
            if any(value is not None for value in fields):
                raise ValueError("NOT_PROVIDED parser evidence must be empty")
        elif any(value is None for value in fields):
            raise ValueError("parser evidence requires complete version and hash identity")
        return self
