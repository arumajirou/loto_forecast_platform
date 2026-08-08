"""Secret and protected-actual redaction for telemetry payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

REDACTED = "[REDACTED]"
PROTECTED_ACTUAL = "[PROTECTED_ACTUAL]"

_SENSITIVE_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "database_url",
    "dsn",
    "passwd",
    "password",
    "private_key",
    "secret",
    "smtp",
    "token",
}
_PROTECTED_ACTUAL_KEYS = {
    "actual",
    "actuals",
    "ground_truth",
    "realized_value",
    "target",
    "targets",
    "winning_numbers",
    "y_true",
}
_URI_USERINFO_RE = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)([^/@\s:]+):([^/@\s]+)@")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:api_key|apikey|password|secret|token)=)[^&#\s]+")


class RevealState(StrEnum):
    """Whether protected actual values may be retained in telemetry."""

    PROTECTED = "PROTECTED"
    AUTHORIZED = "AUTHORIZED"


def _normalise_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def is_sensitive_key(key: str) -> bool:
    """Return whether a key denotes a secret-bearing field."""

    normalised = _normalise_key(key)
    segments = {segment for segment in re.split(r"[._]", normalised) if segment}
    return normalised in _SENSITIVE_PARTS or bool(segments & _SENSITIVE_PARTS)


def is_protected_actual_key(key: str) -> bool:
    """Return whether a key denotes a protected actual/target value."""

    normalised = _normalise_key(key)
    last = normalised.rsplit(".", 1)[-1]
    return normalised in _PROTECTED_ACTUAL_KEYS or last in _PROTECTED_ACTUAL_KEYS


def redact_string(value: str) -> str:
    """Redact URI credentials, bearer tokens, and secret query parameters."""

    redacted = _URI_USERINFO_RE.sub(r"\1[REDACTED]@", value)
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", redacted)
    return _QUERY_SECRET_RE.sub(r"\1[REDACTED]", redacted)


def redact_value(
    value: Any,
    *,
    reveal_state: RevealState = RevealState.PROTECTED,
    key: str | None = None,
    _depth: int = 0,
    max_depth: int = 8,
) -> Any:
    """Recursively redact secrets and protected actuals without mutating input values."""

    if _depth > max_depth:
        return "[MAX_DEPTH]"
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if (
        key is not None
        and is_protected_actual_key(key)
        and reveal_state is not RevealState.AUTHORIZED
    ):
        return PROTECTED_ACTUAL
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, Mapping):
        return {
            str(child_key): redact_value(
                child_value,
                reveal_state=reveal_state,
                key=str(child_key),
                _depth=_depth + 1,
                max_depth=max_depth,
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, tuple):
        return tuple(
            redact_value(
                item,
                reveal_state=reveal_state,
                _depth=_depth + 1,
                max_depth=max_depth,
            )
            for item in value
        )
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [
            redact_value(
                item,
                reveal_state=reveal_state,
                _depth=_depth + 1,
                max_depth=max_depth,
            )
            for item in value
        ]
    return value


def redact_mapping(
    values: Mapping[str, Any],
    *,
    reveal_state: RevealState = RevealState.PROTECTED,
) -> dict[str, Any]:
    """Return a fully redacted copy of a telemetry attribute mapping."""

    return {
        str(key): redact_value(value, reveal_state=reveal_state, key=str(key))
        for key, value in values.items()
    }
