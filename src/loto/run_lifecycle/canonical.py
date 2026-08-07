"""Deterministic canonical JSON and SHA-256 helpers."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel

from .exceptions import LifecycleValidationError


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python", exclude_none=False))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise LifecycleValidationError("canonical datetime must be UTC-aware")
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LifecycleValidationError("canonical JSON rejects NaN and Infinity")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise LifecycleValidationError("canonical JSON object keys must be strings")
            normalized[key] = _normalize(item)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        return [_normalize(item) for item in value]
    raise LifecycleValidationError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return deterministic UTF-8 JSON text for a supported value."""

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def parse_canonical_object(text: str) -> dict[str, Any]:
    """Parse and verify a canonical JSON object string."""

    try:
        parsed = json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(
                LifecycleValidationError(f"non-finite JSON constant: {token}")
            ),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise LifecycleValidationError("invalid JSON object") from exc
    if not isinstance(parsed, dict):
        raise LifecycleValidationError("canonical payload must be a JSON object")
    expected = canonical_json(parsed)
    if text != expected:
        raise LifecycleValidationError("JSON object is valid but not canonical")
    return parsed


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_canonical(value: Any) -> str:
    return sha256_text(canonical_json(value))
