"""Deterministic JSON encoding and identity for telemetry events."""

from __future__ import annotations

import hashlib
import json

from loto.telemetry.contracts import TelemetryEvent


def encode_event_json(event: TelemetryEvent) -> bytes:
    """Encode one event as canonical UTF-8 JSON without non-finite values."""

    return json.dumps(
        event.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def event_sha256(event: TelemetryEvent) -> str:
    """Return SHA-256 over canonical event bytes."""

    return hashlib.sha256(encode_event_json(event)).hexdigest()
