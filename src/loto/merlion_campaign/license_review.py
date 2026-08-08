from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

LICENSE_REVIEW_SCHEMA = "merlion-license-review-v1"
LICENSE_TEMPLATE_SCHEMA = "merlion-license-review-template-v1"
_ALLOWED_DECISIONS = {"APPROVED", "REJECTED", "PENDING"}


def canonical_sha256(payload: Mapping[str, Any], *, omit: str | None = None) -> str:
    filtered = {key: value for key, value in payload.items() if key != omit}
    encoded = json.dumps(filtered, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_dependency_inventory(data: bytes) -> list[dict[str, str]]:
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    required = {"name", "version", "source_kind", "source"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("dependency inventory columns are incomplete")
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in reader:
        row = {str(key): (value or "").strip() for key, value in raw.items()}
        name = row["name"]
        version = row["version"]
        if not name or not version:
            raise ValueError("dependency inventory contains an empty name or version")
        key = (name, version)
        if key in seen:
            raise ValueError(f"dependency inventory contains duplicate package: {name}=={version}")
        seen.add(key)
        rows.append(row)
    if not rows:
        raise ValueError("dependency inventory is empty")
    rows.sort(key=lambda row: (row["name"], row["version"], row["source_kind"]))
    return rows


def _template_origin(payload: Mapping[str, Any]) -> str:
    packages = payload.get("packages", [])
    identities: list[dict[str, str]] = []
    if isinstance(packages, list):
        for package in packages:
            if isinstance(package, Mapping):
                identities.append(
                    {
                        "name": str(package.get("name", "")),
                        "version": str(package.get("version", "")),
                    }
                )
    identities.sort(key=lambda row: (row["name"], row["version"]))
    origin = {
        "schema_version": LICENSE_TEMPLATE_SCHEMA,
        "evidence_zip_sha256": payload.get("evidence_zip_sha256"),
        "lock_sha256": payload.get("lock_sha256"),
        "package_count": payload.get("package_count"),
        "packages": identities,
    }
    return canonical_sha256(origin)


def build_license_review_template(
    inventory_rows: Sequence[Mapping[str, str]],
    *,
    evidence_zip_sha256: str,
    lock_sha256: str,
) -> dict[str, Any]:
    packages: list[dict[str, str]] = []
    for row in inventory_rows:
        if row.get("source_kind") != "registry":
            continue
        packages.append(
            {
                "name": str(row["name"]),
                "version": str(row["version"]),
                "license_expression": "",
                "license_evidence": "",
                "decision": "PENDING",
                "notes": "",
            }
        )
    packages.sort(key=lambda row: (row["name"], row["version"]))
    template: dict[str, Any] = {
        "schema_version": LICENSE_TEMPLATE_SCHEMA,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "reviewer": "",
        "reviewed_at_utc": "",
        "evidence_zip_sha256": evidence_zip_sha256,
        "lock_sha256": lock_sha256,
        "package_count": len(packages),
        "packages": packages,
        "overall_decision": "PENDING",
    }
    template["template_origin_sha256"] = _template_origin(template)
    return template


def finalize_license_review(template: Mapping[str, Any]) -> dict[str, Any]:
    if template.get("schema_version") != LICENSE_TEMPLATE_SCHEMA:
        raise ValueError("license review template schema is invalid")
    recorded = template.get("template_origin_sha256")
    if not isinstance(recorded, str) or recorded != _template_origin(template):
        raise ValueError("license review template origin SHA-256 mismatch")
    if not str(template.get("reviewer", "")).strip():
        raise ValueError("license reviewer is required")
    if not str(template.get("reviewed_at_utc", "")).strip():
        raise ValueError("license review time is required")
    packages = template.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("license review packages are invalid")
    decisions: list[str] = []
    for package in packages:
        if not isinstance(package, Mapping):
            raise ValueError("license review package is invalid")
        name = str(package.get("name", "")).strip()
        version = str(package.get("version", "")).strip()
        decision = str(package.get("decision", "")).strip()
        if decision not in {"APPROVED", "REJECTED"}:
            raise ValueError(f"license decision is unresolved: {name}=={version}")
        if not str(package.get("license_expression", "")).strip():
            raise ValueError(f"license expression is missing: {name}=={version}")
        if not str(package.get("license_evidence", "")).strip():
            raise ValueError(f"license evidence is missing: {name}=={version}")
        decisions.append(decision)
    review = dict(template)
    review.pop("template_origin_sha256", None)
    review["schema_version"] = LICENSE_REVIEW_SCHEMA
    review["overall_decision"] = (
        "APPROVED" if all(value == "APPROVED" for value in decisions) else "REJECTED"
    )
    review["review_sha256"] = canonical_sha256(review)
    return review


def validate_license_review(
    payload: Mapping[str, Any],
    inventory_rows: Sequence[Mapping[str, str]],
    *,
    evidence_zip_sha256: str,
    lock_sha256: str,
) -> tuple[list[str], int]:
    blockers: list[str] = []
    if payload.get("schema_version") != LICENSE_REVIEW_SCHEMA:
        blockers.append("LICENSE_REVIEW_SCHEMA_INVALID")
    recorded_hash = payload.get("review_sha256")
    if not isinstance(recorded_hash, str) or len(recorded_hash) != 64:
        blockers.append("LICENSE_REVIEW_SELF_HASH_MISSING")
    elif recorded_hash != canonical_sha256(payload, omit="review_sha256"):
        blockers.append("LICENSE_REVIEW_SELF_HASH_MISMATCH")
    if payload.get("evidence_zip_sha256") != evidence_zip_sha256:
        blockers.append("LICENSE_REVIEW_EVIDENCE_HASH_MISMATCH")
    if payload.get("lock_sha256") != lock_sha256:
        blockers.append("LICENSE_REVIEW_LOCK_HASH_MISMATCH")
    if not str(payload.get("reviewer", "")).strip():
        blockers.append("LICENSE_REVIEWER_MISSING")
    if not str(payload.get("reviewed_at_utc", "")).strip():
        blockers.append("LICENSE_REVIEW_TIME_MISSING")

    expected = {
        (str(row["name"]), str(row["version"]))
        for row in inventory_rows
        if row.get("source_kind") == "registry"
    }
    packages = payload.get("packages")
    actual: set[tuple[str, str]] = set()
    if not isinstance(packages, list):
        blockers.append("LICENSE_REVIEW_PACKAGES_INVALID")
        packages = []
    for package in packages:
        if not isinstance(package, Mapping):
            blockers.append("LICENSE_REVIEW_PACKAGE_INVALID")
            continue
        name = str(package.get("name", "")).strip()
        version = str(package.get("version", "")).strip()
        key = (name, version)
        if not name or not version:
            blockers.append("LICENSE_REVIEW_PACKAGE_ID_MISSING")
            continue
        if key in actual:
            blockers.append(f"LICENSE_REVIEW_DUPLICATE:{name}=={version}")
        actual.add(key)
        decision = str(package.get("decision", "")).strip()
        if decision not in _ALLOWED_DECISIONS:
            blockers.append(f"LICENSE_DECISION_INVALID:{name}=={version}")
        elif decision != "APPROVED":
            blockers.append(f"LICENSE_NOT_APPROVED:{name}=={version}:{decision}")
        if not str(package.get("license_expression", "")).strip():
            blockers.append(f"LICENSE_EXPRESSION_MISSING:{name}=={version}")
        if not str(package.get("license_evidence", "")).strip():
            blockers.append(f"LICENSE_EVIDENCE_MISSING:{name}=={version}")
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            blockers.append(f"LICENSE_REVIEW_PACKAGES_MISSING:{missing}")
        if extra:
            blockers.append(f"LICENSE_REVIEW_PACKAGES_EXTRA:{extra}")
    if payload.get("package_count") != len(expected):
        blockers.append("LICENSE_REVIEW_PACKAGE_COUNT_MISMATCH")
    if payload.get("overall_decision") != "APPROVED":
        blockers.append("LICENSE_OVERALL_DECISION_NOT_APPROVED")
    return sorted(set(blockers)), len(expected)
