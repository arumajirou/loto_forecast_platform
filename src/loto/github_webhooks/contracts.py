from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


REPOSITORY_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9-]{1,100}$")
GIT_REF_RE = re.compile(r"^refs/[A-Za-z0-9._/\-]{1,240}$")
HEX_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ERROR_CODE_RE = re.compile(r"^[A-Z0-9_]{1,64}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EventType(StrEnum):
    PUSH = "push"
    PULL_REQUEST = "pull_request"
    ISSUES = "issues"
    WORKFLOW_RUN = "workflow_run"


class ProcessingStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSED = "PROCESSED"
    DEAD_LETTER = "DEAD_LETTER"


class StoreOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"


class HandlerStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RETRY = "RETRY"
    SUCCEEDED = "SUCCEEDED"
    DEAD_LETTER = "DEAD_LETTER"


class RepositoryPolicy(StrictModel):
    repository_id: int = Field(gt=0)
    repository_full_name: str = Field(min_length=3, max_length=200)

    @field_validator("repository_full_name")
    @classmethod
    def validate_repository_name(cls, value: str) -> str:
        if not REPOSITORY_NAME_RE.fullmatch(value):
            raise ValueError("repository_full_name must be owner/name")
        return value


class ReceiverPolicy(StrictModel):
    schema_version: Literal[1]
    enabled: bool = False
    repository: RepositoryPolicy
    allowed_actions: dict[EventType, tuple[str | None, ...]]
    max_body_bytes: int = Field(gt=0, le=10 * 1024 * 1024)
    max_attempts: int = Field(ge=1, le=20)
    base_backoff_seconds: int = Field(ge=1, le=3600)
    max_backoff_seconds: int = Field(ge=1, le=86400)
    handler_timeout_seconds: int = Field(ge=1, le=30)
    delivery_retention_days: int = Field(ge=1, le=365)
    history_retention_days: int = Field(ge=1, le=3650)
    dead_letter_retention_days: int = Field(ge=1, le=365)
    dispatch_handlers: tuple[str, ...] = Field(min_length=1, max_length=16)
    forensic_raw_payload_enabled: Literal[False]

    @model_validator(mode="after")
    def validate_policy(self) -> "ReceiverPolicy":
        if set(self.allowed_actions) != set(EventType):
            raise ValueError("allowed_actions must declare every supported event")
        if self.max_backoff_seconds < self.base_backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= base_backoff_seconds")
        if len(self.dispatch_handlers) != len(set(self.dispatch_handlers)):
            raise ValueError("dispatch_handlers must be unique")
        for handler in self.dispatch_handlers:
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", handler):
                raise ValueError(f"invalid dispatch handler {handler!r}")
        for event, actions in self.allowed_actions.items():
            if not actions:
                raise ValueError(f"{event.value} must declare at least one allowed action")
            if len(actions) != len(set(actions)):
                raise ValueError(f"{event.value} has duplicate actions")
            for action in actions:
                if action is not None and not re.fullmatch(r"[a-z_]{1,64}", action):
                    raise ValueError(f"invalid action {action!r}")
        return self


class GitHubWebhookHeaders(StrictModel):
    event_type: EventType
    delivery_id: UUID
    signature_256: str = Field(min_length=71, max_length=71)
    content_type: str = Field(min_length=16, max_length=100)
    hook_id: int | None = Field(default=None, gt=0)
    user_agent: str | None = Field(default=None, max_length=200)


class PushEvent(StrictModel):
    ref: str
    before_sha: str
    after_sha: str
    created: bool
    deleted: bool
    forced: bool
    sender_login: str | None = None


class PullRequestEvent(StrictModel):
    action: str
    number: int = Field(gt=0)
    draft: bool
    merged: bool
    base_ref: str = Field(min_length=1, max_length=255)
    base_sha: str
    head_ref: str = Field(min_length=1, max_length=255)
    head_sha: str
    author_login: str | None = None
    html_url: str = Field(min_length=8, max_length=500)


class IssueEvent(StrictModel):
    action: str
    number: int = Field(gt=0)
    state: Literal["open", "closed"]
    state_reason: str | None = Field(default=None, max_length=64)
    labels: tuple[str, ...] = Field(max_length=50)
    assignees: tuple[str, ...] = Field(max_length=50)
    author_login: str | None = None
    html_url: str = Field(min_length=8, max_length=500)


class WorkflowRunEvent(StrictModel):
    action: str
    workflow_id: int = Field(gt=0)
    run_id: int = Field(gt=0)
    run_attempt: int = Field(ge=1)
    trigger_event: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=64)
    conclusion: str | None = Field(default=None, max_length=64)
    head_branch: str | None = Field(default=None, max_length=255)
    head_sha: str
    execution_classification: Literal[
        "ACTIONS_UNKNOWN",
        "ACTIONS_VERIFIED",
        "CI_BLOCKED_PRE_RUN",
        "ACTIONS_FAILED_ACTIONABLE",
    ]
    html_url: str = Field(min_length=8, max_length=500)


NormalizedPayload = PushEvent | PullRequestEvent | IssueEvent | WorkflowRunEvent


class GitHubWebhookEnvelope(StrictModel):
    schema_version: Literal["1.0.0"]
    delivery_id: UUID
    event_type: EventType
    action: str | None
    repository_id: int = Field(gt=0)
    repository_full_name: str
    sender_login: str | None = None
    ref: str | None = None
    head_sha: str | None = None
    payload_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    received_at: AwareDatetime
    signature_verified: Literal[True]
    key_id: str = Field(min_length=1, max_length=64)
    trace_id: str
    processing_status: Literal[ProcessingStatus.QUEUED]
    attempt: Literal[0]
    normalized: dict[str, Any]

    @field_validator("repository_full_name")
    @classmethod
    def validate_repository_name(cls, value: str) -> str:
        if not REPOSITORY_NAME_RE.fullmatch(value):
            raise ValueError("repository_full_name must be owner/name")
        return value

    @field_validator("sender_login")
    @classmethod
    def validate_sender_login(cls, value: str | None) -> str | None:
        if value is not None and not LOGIN_RE.fullmatch(value):
            raise ValueError("invalid sender login")
        return value

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str | None) -> str | None:
        if value is not None and not GIT_REF_RE.fullmatch(value):
            raise ValueError("invalid git ref")
        return value

    @field_validator("head_sha")
    @classmethod
    def validate_head_sha(cls, value: str | None) -> str | None:
        if value is not None and not HEX_SHA_RE.fullmatch(value):
            raise ValueError("invalid head SHA")
        return value

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        if not TRACE_ID_RE.fullmatch(value):
            raise ValueError("trace_id must be 32 lowercase hex characters")
        return value


class ReceiverResult(StrictModel):
    status_code: int = Field(ge=100, le=599)
    result: Literal[
        "accepted",
        "duplicate",
        "conflict",
        "disabled",
        "rejected",
        "unavailable",
    ]
    delivery_id: str | None = Field(default=None, max_length=64)
    trace_id: str
    processing_status: str | None = Field(default=None, max_length=64)
    error_code: str | None = None

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        if not TRACE_ID_RE.fullmatch(value):
            raise ValueError("trace_id must be 32 lowercase hex characters")
        return value

    @field_validator("error_code")
    @classmethod
    def validate_error_code(cls, value: str | None) -> str | None:
        if value is not None and not ERROR_CODE_RE.fullmatch(value):
            raise ValueError("invalid error code")
        return value


class HandlerClaim(StrictModel):
    claim_id: int = Field(gt=0)
    repository_id: int = Field(gt=0)
    delivery_id: str
    handler: str
    attempt: int = Field(ge=1)
    payload_sha256: str
    normalized_json: str
    trace_id: str
    locked_by: str
    locked_at: datetime
