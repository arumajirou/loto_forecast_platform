from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any


def canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def seal_prospective_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("actual_known") is not False:
        raise ValueError("prospective prediction requires actual_known=false")
    stamped = deepcopy(payload)
    stamped["sealed_at_utc"] = datetime.now(UTC).isoformat()
    stamped["sha256"] = hashlib.sha256(canonical_json(stamped)).hexdigest()
    return stamped


def verify_prediction_seal(payload: dict[str, Any]) -> bool:
    provided = payload.get("sha256")
    unsigned = {key: value for key, value in payload.items() if key != "sha256"}
    expected = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    return isinstance(provided, str) and provided == expected
