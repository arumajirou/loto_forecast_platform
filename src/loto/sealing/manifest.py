from __future__ import annotations

import copy
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def seal_payload(payload: dict, secret: bytes) -> dict:
    frozen = copy.deepcopy(payload); payload_hash=hashlib.sha256(_canonical_bytes(frozen)).hexdigest()
    signature=hmac.new(secret,payload_hash.encode(),hashlib.sha256).hexdigest()
    return {"algorithm":"HMAC-SHA256","sealed_at":datetime.now(UTC).isoformat(),"payload_sha256":payload_hash,
            "signature":signature,"payload":frozen}


def verify_seal(sealed: dict, secret: bytes) -> bool:
    try:
        actual=hashlib.sha256(_canonical_bytes(sealed["payload"])).hexdigest()
        if not hmac.compare_digest(actual,sealed["payload_sha256"]): return False
        expected=hmac.new(secret,actual.encode(),hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected,sealed["signature"])
    except (KeyError, TypeError): return False
