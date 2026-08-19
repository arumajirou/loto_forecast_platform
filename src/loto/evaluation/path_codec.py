"""Portable filesystem encoding for logical campaign identifiers."""

from __future__ import annotations

import base64
import binascii
import re

_PORTABLE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")
_WINDOWS_RESERVED_STEMS = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _is_portable_component(value: str) -> bool:
    if not _PORTABLE_COMPONENT.fullmatch(value):
        return False

    if value in {".", ".."}:
        return False

    if value.endswith("."):
        return False

    stem = value.split(".", 1)[0].upper()

    return stem not in _WINDOWS_RESERVED_STEMS


def encode_path_component(value: str) -> str:
    """Encode a logical ID as a reversible portable path component."""
    if not value:
        raise ValueError("path component must not be empty")

    if _is_portable_component(value):
        return value

    token = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")

    return f"~{token}"


def decode_path_component(value: str) -> str:
    """Decode a portable filesystem component to its logical ID."""
    if not value:
        raise ValueError("path component must not be empty")

    if not value.startswith("~"):
        if not _is_portable_component(value):
            raise ValueError("non-canonical portable path component")
        return value

    token = value[1:]

    if not token:
        raise ValueError("encoded path component must not be empty")

    padding = "=" * (-len(token) % 4)

    try:
        decoded = base64.urlsafe_b64decode(token + padding).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("invalid encoded path component") from exc

    if encode_path_component(decoded) != value:
        raise ValueError("non-canonical encoded path component")

    return decoded
