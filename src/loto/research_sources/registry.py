from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .index import ResearchSourceRegistryIndex
from .models import ResearchSourceRegistry


class DuplicateJsonKeyError(ValueError):
    """Raised when a registry JSON object contains duplicate keys."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_registry(path: str | Path) -> ResearchSourceRegistry:
    """Load and strictly validate a Research Source Registry JSON document."""
    registry_path = Path(path)
    payload = json.loads(
        registry_path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant rejected: {value}")
        ),
    )
    if isinstance(payload, dict) and "record_files" in payload:
        index = ResearchSourceRegistryIndex.model_validate_json(
            json.dumps(payload, ensure_ascii=False, allow_nan=False)
        )
        root = registry_path.resolve().parent
        records: list[dict[str, Any]] = []
        for relative_name in index.record_files:
            record_path = (root / relative_name).resolve()
            if root not in record_path.parents:
                raise ValueError(f"record file escapes registry directory: {relative_name}")
            record_payload = json.loads(
                record_path.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant rejected: {value}")
                ),
            )
            if not isinstance(record_payload, dict):
                raise ValueError(f"record file must contain a JSON object: {relative_name}")
            records.append(record_payload)
        payload = {
            "schema_version": index.schema_version,
            "generated_at": index.generated_at.isoformat(),
            "records": records,
        }
    normalized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return ResearchSourceRegistry.model_validate_json(normalized)


def canonical_registry_bytes(registry: ResearchSourceRegistry) -> bytes:
    """Return deterministic UTF-8 JSON bytes for registry identity."""
    payload = registry.model_dump(mode="json")
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def registry_sha256(registry: ResearchSourceRegistry) -> str:
    """Return the lowercase SHA-256 of the canonical registry payload."""
    return hashlib.sha256(canonical_registry_bytes(registry)).hexdigest()


def validation_report(registry: ResearchSourceRegistry) -> dict[str, Any]:
    """Build a non-promotional machine-readable validation report."""
    statuses: dict[str, int] = {}
    for record in registry.records:
        status = record.verification.status.value
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "schema_version": registry.schema_version,
        "status": "VALID",
        "record_count": len(registry.records),
        "status_counts": dict(sorted(statuses.items())),
        "registry_sha256": registry_sha256(registry),
        "runtime_success": False,
        "production_eligibility": False,
        "non_claim": "registry validation is source-intake validation only",
    }
