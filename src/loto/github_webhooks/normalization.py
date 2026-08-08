from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from loto.github_webhooks.contracts import (
    EventType,
    GitHubWebhookEnvelope,
    GitHubWebhookHeaders,
    IssueEvent,
    PullRequestEvent,
    PushEvent,
    ReceiverPolicy,
    WorkflowRunEvent,
)


class WebhookNormalizationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def classify_workflow_execution(
    *,
    steps: list[dict[str, Any]] | None,
    logs_available: bool | None,
    conclusion: str | None,
) -> str:
    if steps is None or (not steps and logs_available is False):
        return "CI_BLOCKED_PRE_RUN"
    if steps and logs_available is True:
        if conclusion in {None, "success"}:
            return "ACTIONS_VERIFIED"
        return "ACTIONS_FAILED_ACTIONABLE"
    return "ACTIONS_UNKNOWN"


def _mapping(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WebhookNormalizationError(code)
    return value


def _string(value: Any, code: str) -> str:
    if not isinstance(value, str):
        raise WebhookNormalizationError(code)
    return value


def _boolean(value: Any, code: str) -> bool:
    if not isinstance(value, bool):
        raise WebhookNormalizationError(code)
    return value


def _optional_login(value: Any) -> str | None:
    if value is None:
        return None
    mapping = _mapping(value, "SENDER_INVALID")
    login = mapping.get("login")
    return None if login is None else _string(login, "SENDER_LOGIN_INVALID")


def _sha(value: Any, code: str) -> str:
    sha = _string(value, code).lower()
    if len(sha) not in {40, 64} or any(char not in "0123456789abcdef" for char in sha):
        raise WebhookNormalizationError(code)
    return sha


def _repository(payload: dict[str, Any], policy: ReceiverPolicy) -> tuple[int, str]:
    repository = _mapping(payload.get("repository"), "REPOSITORY_MISSING")
    repository_id = repository.get("id")
    full_name = repository.get("full_name")
    if not isinstance(repository_id, int) or repository_id <= 0:
        raise WebhookNormalizationError("REPOSITORY_ID_INVALID")
    if not isinstance(full_name, str):
        raise WebhookNormalizationError("REPOSITORY_NAME_INVALID")
    expected = policy.repository
    if repository_id != expected.repository_id or full_name != expected.repository_full_name:
        raise WebhookNormalizationError("REPOSITORY_NOT_ALLOWED")
    return repository_id, full_name


def _validate_action(
    event_type: EventType,
    payload: dict[str, Any],
    policy: ReceiverPolicy,
) -> str | None:
    action_value = payload.get("action")
    if action_value is not None and not isinstance(action_value, str):
        raise WebhookNormalizationError("ACTION_INVALID")
    action = action_value
    if action not in policy.allowed_actions[event_type]:
        raise WebhookNormalizationError("ACTION_NOT_ALLOWED")
    return action


def _push(payload: dict[str, Any]) -> PushEvent:
    try:
        return PushEvent(
            ref=_string(payload.get("ref"), "PUSH_REF_INVALID"),
            before_sha=_sha(payload.get("before"), "PUSH_BEFORE_INVALID"),
            after_sha=_sha(payload.get("after"), "PUSH_AFTER_INVALID"),
            created=_boolean(payload.get("created"), "PUSH_CREATED_INVALID"),
            deleted=_boolean(payload.get("deleted"), "PUSH_DELETED_INVALID"),
            forced=_boolean(payload.get("forced"), "PUSH_FORCED_INVALID"),
            sender_login=_optional_login(payload.get("sender")),
        )
    except ValidationError as exc:
        raise WebhookNormalizationError("PUSH_SCHEMA_INVALID") from exc


def _pull_request(payload: dict[str, Any], action: str | None) -> PullRequestEvent:
    if action is None:
        raise WebhookNormalizationError("ACTION_REQUIRED")
    pr = _mapping(payload.get("pull_request"), "PULL_REQUEST_MISSING")
    base = _mapping(pr.get("base"), "PULL_REQUEST_BASE_INVALID")
    head = _mapping(pr.get("head"), "PULL_REQUEST_HEAD_INVALID")
    user = _mapping(pr.get("user"), "PULL_REQUEST_USER_INVALID")
    try:
        return PullRequestEvent(
            action=action,
            number=payload.get("number"),
            draft=_boolean(pr.get("draft"), "PULL_REQUEST_DRAFT_INVALID"),
            merged=_boolean(pr.get("merged"), "PULL_REQUEST_MERGED_INVALID"),
            base_ref=_string(base.get("ref"), "PULL_REQUEST_BASE_REF_INVALID"),
            base_sha=_sha(base.get("sha"), "PULL_REQUEST_BASE_SHA_INVALID"),
            head_ref=_string(head.get("ref"), "PULL_REQUEST_HEAD_REF_INVALID"),
            head_sha=_sha(head.get("sha"), "PULL_REQUEST_HEAD_SHA_INVALID"),
            author_login=user.get("login"),
            html_url=_string(pr.get("html_url"), "PULL_REQUEST_URL_INVALID"),
        )
    except ValidationError as exc:
        raise WebhookNormalizationError("PULL_REQUEST_SCHEMA_INVALID") from exc


def _issues(payload: dict[str, Any], action: str | None) -> IssueEvent:
    if action is None:
        raise WebhookNormalizationError("ACTION_REQUIRED")
    issue = _mapping(payload.get("issue"), "ISSUE_MISSING")
    user = _mapping(issue.get("user"), "ISSUE_USER_INVALID")
    labels_raw = issue.get("labels", [])
    assignees_raw = issue.get("assignees", [])
    if not isinstance(labels_raw, list) or not isinstance(assignees_raw, list):
        raise WebhookNormalizationError("ISSUE_LIST_INVALID")
    labels = []
    for item in labels_raw[:50]:
        label = _mapping(item, "ISSUE_LABEL_INVALID")
        labels.append(_string(label.get("name"), "ISSUE_LABEL_NAME_INVALID")[:100])
    assignees = []
    for item in assignees_raw[:50]:
        assignee = _mapping(item, "ISSUE_ASSIGNEE_INVALID")
        assignees.append(_string(assignee.get("login"), "ISSUE_ASSIGNEE_LOGIN_INVALID"))
    try:
        return IssueEvent(
            action=action,
            number=issue.get("number"),
            state=issue.get("state"),
            state_reason=issue.get("state_reason"),
            labels=tuple(labels),
            assignees=tuple(assignees),
            author_login=user.get("login"),
            html_url=_string(issue.get("html_url"), "ISSUE_URL_INVALID"),
        )
    except ValidationError as exc:
        raise WebhookNormalizationError("ISSUE_SCHEMA_INVALID") from exc


def _workflow_run(payload: dict[str, Any], action: str | None) -> WorkflowRunEvent:
    if action is None:
        raise WebhookNormalizationError("ACTION_REQUIRED")
    run = _mapping(payload.get("workflow_run"), "WORKFLOW_RUN_MISSING")
    steps = payload.get("_verification_steps")
    if steps is not None and not isinstance(steps, list):
        raise WebhookNormalizationError("WORKFLOW_STEPS_INVALID")
    logs_available = payload.get("_verification_logs_available")
    if logs_available is not None and not isinstance(logs_available, bool):
        raise WebhookNormalizationError("WORKFLOW_LOGS_INVALID")
    try:
        return WorkflowRunEvent(
            action=action,
            workflow_id=run.get("workflow_id"),
            run_id=run.get("id"),
            run_attempt=run.get("run_attempt", 1),
            trigger_event=_string(run.get("event"), "WORKFLOW_EVENT_INVALID"),
            status=_string(run.get("status"), "WORKFLOW_STATUS_INVALID"),
            conclusion=run.get("conclusion"),
            head_branch=run.get("head_branch"),
            head_sha=_sha(run.get("head_sha"), "WORKFLOW_HEAD_SHA_INVALID"),
            execution_classification=classify_workflow_execution(
                steps=steps,
                logs_available=logs_available,
                conclusion=run.get("conclusion"),
            ),
            html_url=_string(run.get("html_url"), "WORKFLOW_URL_INVALID"),
        )
    except ValidationError as exc:
        raise WebhookNormalizationError("WORKFLOW_RUN_SCHEMA_INVALID") from exc


def normalize_delivery(
    *,
    headers: GitHubWebhookHeaders,
    payload: dict[str, Any],
    payload_sha256: str,
    policy: ReceiverPolicy,
    key_id: str,
    trace_id: str,
    received_at: datetime | None = None,
) -> GitHubWebhookEnvelope:
    repository_id, repository_full_name = _repository(payload, policy)
    action = _validate_action(headers.event_type, payload, policy)
    sender_login = _optional_login(payload.get("sender"))

    if headers.event_type is EventType.PUSH:
        normalized = _push(payload)
        ref = normalized.ref
        head_sha = normalized.after_sha
    elif headers.event_type is EventType.PULL_REQUEST:
        normalized = _pull_request(payload, action)
        ref = f"refs/heads/{normalized.head_ref}"
        head_sha = normalized.head_sha
    elif headers.event_type is EventType.ISSUES:
        normalized = _issues(payload, action)
        ref = None
        head_sha = None
    else:
        normalized = _workflow_run(payload, action)
        ref = f"refs/heads/{normalized.head_branch}" if normalized.head_branch is not None else None
        head_sha = normalized.head_sha

    timestamp = received_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise WebhookNormalizationError("RECEIVED_AT_NAIVE")
    return GitHubWebhookEnvelope(
        schema_version="1.0.0",
        delivery_id=UUID(str(headers.delivery_id)),
        event_type=headers.event_type,
        action=action,
        repository_id=repository_id,
        repository_full_name=repository_full_name,
        sender_login=sender_login,
        ref=ref,
        head_sha=head_sha,
        payload_sha256=payload_sha256,
        received_at=timestamp.astimezone(UTC),
        signature_verified=True,
        key_id=key_id,
        trace_id=trace_id,
        processing_status="QUEUED",
        attempt=0,
        normalized=normalized.model_dump(mode="json"),
    )
