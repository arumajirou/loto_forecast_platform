"""Canonical hashing helpers used by evidence schemas and offline verification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_headers(headers: Mapping[str, str | Sequence[str]]) -> list[list[str]]:
    normalized: list[list[str]] = []
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip().casefold()
        if not name:
            raise ValueError("header name must not be empty")
        if isinstance(raw_value, str):
            values = [raw_value]
        else:
            values = [str(item) for item in raw_value]
        normalized.append([name, "\n".join(value.strip() for value in values)])
    normalized.sort(key=lambda item: (item[0], item[1]))
    return normalized


def headers_sha256(headers: Mapping[str, str | Sequence[str]]) -> str:
    return canonical_sha256(canonical_headers(headers))


def material_inventory_sha256(materials: Sequence[Mapping[str, Any]]) -> str:
    inventory = [
        {
            "material_id": str(item["material_id"]),
            "relative_path": str(item["relative_path"]),
            "sha256": str(item["sha256"]),
            "size_bytes": int(item["size_bytes"]),
            "role": str(item["role"]),
        }
        for item in materials
    ]
    inventory.sort(key=lambda item: (item["relative_path"], item["material_id"]))
    return canonical_sha256(inventory)
