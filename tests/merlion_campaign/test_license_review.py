from __future__ import annotations

import csv
import io

import pytest

from loto.merlion_campaign.license_review import (
    LICENSE_REVIEW_SCHEMA,
    build_license_review_template,
    canonical_sha256,
    finalize_license_review,
)


def _inventory_rows() -> list[dict[str, str]]:
    data = """name,version,source_kind,source
loto-merlion-provider,0.1.0,virtual,.
numpy,1.26.4,registry,https://pypi.org/simple
salesforce-merlion,2.0.4,registry,https://pypi.org/simple
"""
    return list(csv.DictReader(io.StringIO(data)))


def test_license_template_is_pending_and_registry_only() -> None:
    template = build_license_review_template(
        _inventory_rows(),
        evidence_zip_sha256="c" * 64,
        lock_sha256="d" * 64,
    )
    assert template["package_count"] == 2
    assert {row["decision"] for row in template["packages"]} == {"PENDING"}
    assert {row["name"] for row in template["packages"]} == {
        "numpy",
        "salesforce-merlion",
    }


def _completed_template() -> dict[str, object]:
    template = build_license_review_template(
        _inventory_rows(),
        evidence_zip_sha256="c" * 64,
        lock_sha256="d" * 64,
    )
    template["reviewer"] = "reviewer@example.invalid"
    template["reviewed_at_utc"] = "2026-08-05T00:00:00+00:00"
    for package in template["packages"]:
        package["decision"] = "APPROVED"
        package["license_expression"] = "LicenseRef-reviewed"
        package["license_evidence"] = "manual evidence"
    return template


def test_finalize_license_review_hashes_human_decisions() -> None:
    review = finalize_license_review(_completed_template())
    assert review["schema_version"] == LICENSE_REVIEW_SCHEMA
    assert review["overall_decision"] == "APPROVED"
    assert review["review_sha256"] == canonical_sha256(review, omit="review_sha256")


def test_finalize_allows_review_edits_but_rejects_identity_drift() -> None:
    template = _completed_template()
    assert finalize_license_review(template)["overall_decision"] == "APPROVED"
    template["packages"][0]["version"] = "999.0"
    with pytest.raises(ValueError, match="origin SHA-256 mismatch"):
        finalize_license_review(template)


def test_finalize_rejects_pending_decision() -> None:
    template = _completed_template()
    template["packages"][0]["decision"] = "PENDING"
    with pytest.raises(ValueError, match="decision is unresolved"):
        finalize_license_review(template)
