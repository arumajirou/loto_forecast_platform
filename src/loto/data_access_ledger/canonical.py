from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from loto.data_access_ledger.contracts import AccessEvent, DataAccessLedger


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical datetime must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NaN and infinity are forbidden")
        return value
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            normalized[key] = _normalize(item)
        return normalized
    if isinstance(value, (set, frozenset, bytes, bytearray, memoryview, tuple)):
        raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    normalized = _normalize(value)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def compute_ledger_sha256(ledger: DataAccessLedger | dict[str, Any]) -> str:
    if isinstance(ledger, DataAccessLedger):
        payload = ledger.model_dump(mode="python")
    else:
        payload = dict(ledger)
    payload.pop("ledger_sha256", None)
    return sha256_hex(payload)


def seal_ledger(ledger: DataAccessLedger) -> DataAccessLedger:
    return ledger.model_copy(update={"ledger_sha256": compute_ledger_sha256(ledger)})


def build_ledger(
    *,
    run_id: str,
    created_at: datetime,
    events: list[AccessEvent],
    expected_seeds: list[int] | None = None,
) -> DataAccessLedger:
    if not events:
        raise ValueError("events must not be empty")
    draft = DataAccessLedger(
        run_id=run_id,
        created_at=created_at,
        events=events,
        event_count=len(events),
        first_event_at=events[0].occurred_at,
        last_event_at=events[-1].occurred_at,
        ledger_sha256="0" * 64,
        expected_seeds=expected_seeds or [],
    )
    return seal_ledger(draft)
