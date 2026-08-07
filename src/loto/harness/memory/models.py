from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ClaimType(StrEnum):
    OBSERVATION = "OBSERVATION"
    HYPOTHESIS = "HYPOTHESIS"
    DECISION = "DECISION"
    REJECTED = "REJECTED"
    TEST_RESULT = "TEST_RESULT"
    CONSTRAINT = "CONSTRAINT"
    SUPERSEDED = "SUPERSEDED"


class MemoryEvent(BaseModel):
    event_id: str
    project: str
    task_id: str
    event_type: str
    payload: dict[str, Any]
    source: str
    commit_sha: str | None = None
    branch: str | None = None
    protocol_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryClaim(BaseModel):
    claim_id: str
    project: str
    task_id: str
    claim_type: ClaimType
    statement: str
    source_event_id: str
    verified: bool = False
    supersedes_claim_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
