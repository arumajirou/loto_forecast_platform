"""Canonical JSON and SHA-256 helpers for sandbox evidence."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented by the evidence codec."""


def _duplicate_key(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise CanonicalizationError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_key,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CanonicalizationError(f"non-finite JSON constant: {token}")
            ),
        )
    except (json.JSONDecodeError, CanonicalizationError) as exc:
        raise CanonicalizationError(str(exc)) from exc
    if not isinstance(value, dict):
        raise CanonicalizationError("JSON root must be an object")
    return value


def _normalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise CanonicalizationError("datetime must be timezone-aware UTC")
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, PurePosixPath):
        return str(value)
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("canonical JSON object keys must be strings")
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("non-finite numbers are forbidden")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise CanonicalizationError(f"unsupported canonical type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_canonical(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))
