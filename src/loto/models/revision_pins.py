"""Validated revision-pin manifests for time-series foundation models.

This module never guesses or resolves a revision.  It only accepts explicit,
reviewable commit identifiers and verifies that they match the current catalog
model and repository identifiers before applying them to immutable ModelEntry
objects.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loto.models.catalog_full import ModelEntry

SCHEMA_VERSION = 1
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class RevisionPinError(ValueError):
    """Raised when a revision-pin manifest violates the fail-closed contract."""


def validate_revision(value: str) -> str:
    """Return a normalized commit hash or raise.

    Hugging Face and Git repositories normally expose 40-character SHA-1 commit
    identifiers; 64-character SHA-256 identifiers are accepted for repositories
    using the newer object format. Branches, tags and abbreviated hashes are
    rejected because they are mutable or ambiguous.
    """
    normalized = value.strip().lower()
    if not _COMMIT_RE.fullmatch(normalized):
        raise RevisionPinError(
            "revision must be a full 40- or 64-character lowercase hexadecimal commit id"
        )
    return normalized


def template_manifest(entries: Sequence[ModelEntry]) -> dict[str, Any]:
    """Create a deterministic review template for all currently unpinned entries."""
    pins = [
        {
            "model_id": entry.model_id,
            "repo_id": entry.repo_id,
            "revision": "",
            "source": "",
            "verified_at": "",
        }
        for entry in sorted(entries, key=lambda item: item.model_id)
        if entry.revision_status == "UNPINNED"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "pins": pins,
    }


def _read_manifest(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    path = Path(source)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionPinError(f"cannot read revision-pin manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RevisionPinError("revision-pin manifest root must be an object")
    return payload


def validate_manifest(
    source: str | Path | Mapping[str, Any],
    entries: Sequence[ModelEntry],
    *,
    require_complete: bool = False,
) -> dict[str, str]:
    """Validate a manifest and return ``model_id -> revision``.

    Validation is fail-closed: unknown models, repository mismatches, duplicates,
    blank revisions and mutable revision names are rejected.  ``require_complete``
    additionally requires every currently unpinned catalog model to be present.
    """
    payload = _read_manifest(source)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise RevisionPinError(
            f"unsupported schema_version: {payload.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION}"
        )
    rows = payload.get("pins")
    if not isinstance(rows, list):
        raise RevisionPinError("pins must be an array")

    by_id = {entry.model_id: entry for entry in entries}
    result: dict[str, str] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise RevisionPinError(f"pins[{index}] must be an object")
        model_id = str(row.get("model_id", "")).strip()
        repo_id = str(row.get("repo_id", "")).strip()
        revision_raw = str(row.get("revision", "")).strip()
        if not model_id:
            raise RevisionPinError(f"pins[{index}].model_id is required")
        if model_id in result:
            raise RevisionPinError(f"duplicate model_id in manifest: {model_id}")
        entry = by_id.get(model_id)
        if entry is None:
            raise RevisionPinError(f"unknown catalog model_id: {model_id}")
        if entry.repo_id is None:
            raise RevisionPinError(f"model does not support repository revision pins: {model_id}")
        if repo_id != entry.repo_id:
            raise RevisionPinError(
                f"repo_id mismatch for {model_id}: manifest={repo_id!r}, catalog={entry.repo_id!r}"
            )
        result[model_id] = validate_revision(revision_raw)

    if require_complete:
        expected = {entry.model_id for entry in entries if entry.revision_status == "UNPINNED"}
        missing = sorted(expected - result.keys())
        extra = sorted(result.keys() - expected)
        if missing or extra:
            raise RevisionPinError(
                f"complete manifest mismatch: missing={missing}, unexpected={extra}"
            )
    return result


def apply_manifest(
    entries: Sequence[ModelEntry],
    source: str | Path | Mapping[str, Any],
    *,
    require_complete: bool = False,
) -> list[ModelEntry]:
    """Return new immutable catalog entries with validated revisions applied."""
    pins = validate_manifest(source, entries, require_complete=require_complete)
    return [replace(entry, revision=pins.get(entry.model_id, entry.revision)) for entry in entries]


def revision_report(entries: Iterable[ModelEntry]) -> dict[str, Any]:
    rows = [entry.to_row() for entry in entries if entry.repo_id is not None]
    pinned = [row for row in rows if row["revision_status"] == "PINNED"]
    unpinned = [row for row in rows if row["revision_status"] == "UNPINNED"]
    return {
        "total_repository_models": len(rows),
        "pinned": len(pinned),
        "unpinned": len(unpinned),
        "complete": not unpinned,
        "pinned_models": [row["model_id"] for row in pinned],
        "unpinned_models": [row["model_id"] for row in unpinned],
    }
