"""Deterministic verification seals for immutable campaign runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .persistence import sha256_file, write_json

SEAL_SCHEMA_VERSION = "all-auto-verification-seal-v1"
SEAL_CONTRACT_VERSION = "promotion-lineage-verifier-v1"
_MUTABLE_ROOT_FILES = {
    "SHA256SUMS",
    "VERIFICATION_REPORT.json",
    "VERIFICATION_SEAL.json",
}


def _content_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise ValueError(f"verification seal root is not a directory: {root}")
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError(f"verification seal does not allow symlinks: {relative}")
        if not path.is_file():
            continue
        if relative in _MUTABLE_ROOT_FILES:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def content_fingerprint(root: Path) -> tuple[str, int]:
    """Hash every immutable run file using path-and-content framing."""

    digest = hashlib.sha256()
    files = _content_files(root)
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest(), len(files)


def _optional_file_hash(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def _component_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    coverage = result.get("coverage_state_verification")
    promotion = result.get("promotion_gate_verification")
    lineage = result.get("lineage_verification")
    prediction = result.get("prediction_lock_verification")
    prediction_status = prediction.get("status") if isinstance(prediction, Mapping) else None
    if prediction_status == "NOT_APPLICABLE":
        prediction_status = None
    return {
        "overall_status": result.get("status"),
        "legacy_manifest_status": result.get("run_manifest_status"),
        "coverage_status": coverage.get("status") if isinstance(coverage, Mapping) else None,
        "promotion_status": (promotion.get("status") if isinstance(promotion, Mapping) else None),
        "lineage_status": lineage.get("status") if isinstance(lineage, Mapping) else None,
        "prediction_lock_status": prediction_status,
        "failure_count": len(result.get("failures") or []),
    }


def _stable_payload(
    root: Path,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    content_sha256, file_count = content_fingerprint(root)
    return {
        "schema_version": SEAL_SCHEMA_VERSION,
        "contract_version": SEAL_CONTRACT_VERSION,
        "status": "PASS",
        "content_sha256": content_sha256,
        "content_file_count": file_count,
        "manifest_sha256": _optional_file_hash(root / "manifest.json"),
        "promotion_gate_sha256": _optional_file_hash(root / "PROMOTION_GATE.json"),
        "lineage_sha256": _optional_file_hash(root / "LINEAGE.json"),
        "prediction_lock_sha256": _optional_file_hash(root / "PREDICTION_LOCK.json"),
        "components": _component_summary(result),
    }


def _normalize_existing_stable(existing: Mapping[str, Any]) -> dict[str, Any]:
    stable = {key: value for key, value in existing.items() if key != "sealed_at"}
    stable.setdefault("prediction_lock_sha256", None)
    components = stable.get("components")
    if isinstance(components, Mapping):
        normalized_components = dict(components)
        normalized_components.setdefault("prediction_lock_status", None)
        stable["components"] = normalized_components
    return stable


def write_verification_seal(
    root: Path,
    result: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Write a PASS seal while preserving any prior seal after a failure."""

    target = root / "VERIFICATION_SEAL.json"
    if result.get("status") != "PASS":
        return None

    stable = _stable_payload(root, result)
    sealed_at = datetime.now(UTC).isoformat()
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if isinstance(existing, dict):
            existing_stable = _normalize_existing_stable(existing)
            if existing_stable == stable and str(existing.get("sealed_at") or "").strip():
                return existing

    payload = {**stable, "sealed_at": sealed_at}
    write_json(target, payload)
    return payload


def verify_verification_seal(root: Path) -> dict[str, Any]:
    """Reject stale PASS reports whose verified content has since changed."""

    failures: list[str] = []
    path = root / "VERIFICATION_SEAL.json"
    if not path.is_file():
        return {
            "status": "FAIL",
            "content_sha256": None,
            "failures": ["VERIFICATION_SEAL.json missing"],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "FAIL",
            "content_sha256": None,
            "failures": [f"verification seal unreadable: {type(exc).__name__}: {exc}"],
        }
    if not isinstance(payload, dict) or not payload:
        return {
            "status": "FAIL",
            "content_sha256": None,
            "failures": ["verification seal must be a non-empty JSON object"],
        }

    if payload.get("schema_version") != SEAL_SCHEMA_VERSION:
        failures.append("verification seal schema_version mismatch")
    if payload.get("contract_version") != SEAL_CONTRACT_VERSION:
        failures.append("verification seal contract_version mismatch")
    if payload.get("status") != "PASS":
        failures.append("verification seal status must be PASS")
    if not str(payload.get("sealed_at") or "").strip():
        failures.append("verification seal sealed_at missing")

    try:
        current_sha256, current_count = content_fingerprint(root)
    except (OSError, ValueError) as exc:
        failures.append(f"verification seal content unreadable: {type(exc).__name__}: {exc}")
        current_sha256, current_count = None, None
    if payload.get("content_sha256") != current_sha256:
        failures.append(
            "verification seal content hash mismatch: "
            f"recorded={payload.get('content_sha256')}, current={current_sha256}"
        )
    if payload.get("content_file_count") != current_count:
        failures.append(
            "verification seal file count mismatch: "
            f"recorded={payload.get('content_file_count')}, current={current_count}"
        )

    for field, filename in (
        ("manifest_sha256", "manifest.json"),
        ("promotion_gate_sha256", "PROMOTION_GATE.json"),
        ("lineage_sha256", "LINEAGE.json"),
        ("prediction_lock_sha256", "PREDICTION_LOCK.json"),
    ):
        try:
            current = _optional_file_hash(root / filename)
        except OSError as exc:
            failures.append(
                f"verification seal cannot hash {filename}: {type(exc).__name__}: {exc}"
            )
            current = None
        if payload.get(field) != current:
            failures.append(
                f"verification seal {field} mismatch: "
                f"recorded={payload.get(field)}, current={current}"
            )

    components = payload.get("components")
    if not isinstance(components, Mapping) or components.get("overall_status") != "PASS":
        failures.append("verification seal components do not record overall PASS")
    if (root / "PREDICTION_LOCK.json").is_file():
        if not isinstance(components, Mapping):
            failures.append("verification seal prediction components missing")
        elif components.get("prediction_lock_status") != "PASS":
            failures.append("verification seal does not record prediction lock PASS")

    return {
        "status": "PASS" if not failures else "FAIL",
        "content_sha256": current_sha256,
        "content_file_count": current_count,
        "sealed_at": payload.get("sealed_at"),
        "failures": failures,
    }
