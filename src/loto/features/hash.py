from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def frame_hash(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    payload = normalized.to_json(orient="split", date_format="iso", double_precision=15)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def protocol_hash(
    *, feature_manifest: Mapping[str, Any], cutoff: Any, transforms: Iterable[Any]
) -> str:
    return stable_hash(
        {"feature_manifest": feature_manifest, "cutoff": cutoff, "transforms": list(transforms)}
    )
