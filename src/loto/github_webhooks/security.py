from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any

SIGNATURE_RE = re.compile(r"^sha256=([0-9a-fA-F]{64})$")


class WebhookSecurityError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DuplicateJsonKeyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SecretKey:
    key_id: str
    secret: bytes

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", self.key_id):
            raise ValueError("invalid key_id")
        if not self.secret or len(self.secret) > 4096:
            raise ValueError("secret must contain 1..4096 bytes")


@dataclass(frozen=True, slots=True)
class SecretRing:
    active: SecretKey
    previous: SecretKey | None = None

    def __post_init__(self) -> None:
        if self.previous is not None and self.previous.key_id == self.active.key_id:
            raise ValueError("active and previous key IDs must differ")

    @property
    def keys(self) -> tuple[SecretKey, ...]:
        return (self.active,) if self.previous is None else (self.active, self.previous)


def payload_sha256(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def parse_signature_header(value: str | None) -> str:
    if value is None:
        raise WebhookSecurityError("SIGNATURE_MISSING")
    match = SIGNATURE_RE.fullmatch(value.strip())
    if match is None:
        raise WebhookSecurityError("SIGNATURE_MALFORMED")
    return "sha256=" + match.group(1).lower()


def verify_signature(raw_body: bytes, signature_header: str | None, ring: SecretRing) -> str:
    received = parse_signature_header(signature_header)
    matched_key_id: str | None = None
    for key in ring.keys:
        expected = "sha256=" + hmac.new(key.secret, raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, received):
            matched_key_id = key.key_id
    if matched_key_id is None:
        raise WebhookSecurityError("SIGNATURE_INVALID")
    return matched_key_id


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads_json_object(raw_body: bytes) -> dict[str, Any]:
    try:
        decoded = raw_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WebhookSecurityError("BODY_NOT_UTF8") from exc
    try:
        value = json.loads(decoded, object_pairs_hook=_reject_duplicate_pairs)
    except DuplicateJsonKeyError:
        raise
    except json.JSONDecodeError as exc:
        raise WebhookSecurityError("JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise WebhookSecurityError("JSON_ROOT_NOT_OBJECT")
    return value
