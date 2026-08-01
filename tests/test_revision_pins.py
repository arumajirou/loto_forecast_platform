import json

import pytest

from loto.models.catalog_full import build_catalog
from loto.models.revision_pins import (
    RevisionPinError,
    apply_manifest,
    revision_report,
    template_manifest,
    validate_manifest,
    validate_revision,
)

REV = "a" * 40


def _one_pin():
    entries = build_catalog()
    entry = next(item for item in entries if item.revision_status == "UNPINNED")
    manifest = {
        "schema_version": 1,
        "pins": [{"model_id": entry.model_id, "repo_id": entry.repo_id, "revision": REV}],
    }
    return entries, entry, manifest


def test_full_commit_hash_only():
    assert validate_revision(REV.upper()) == REV
    for value in ("main", "v1.0", "abc123", "g" * 40, "a" * 39, "a" * 41):
        with pytest.raises(RevisionPinError):
            validate_revision(value)


def test_valid_manifest_applies_without_mutating_original():
    entries, target, manifest = _one_pin()
    updated = apply_manifest(entries, manifest)
    original = next(item for item in entries if item.model_id == target.model_id)
    applied = next(item for item in updated if item.model_id == target.model_id)
    assert original.revision is None
    assert applied.revision == REV
    assert applied.revision_status == "PINNED"
    assert entries is not updated


def test_repo_mismatch_unknown_and_duplicate_fail_closed():
    entries, target, manifest = _one_pin()
    bad_repo = json.loads(json.dumps(manifest))
    bad_repo["pins"][0]["repo_id"] = "someone/else"
    with pytest.raises(RevisionPinError, match="repo_id mismatch"):
        validate_manifest(bad_repo, entries)

    unknown = json.loads(json.dumps(manifest))
    unknown["pins"][0]["model_id"] = "unknown-model"
    with pytest.raises(RevisionPinError, match="unknown catalog"):
        validate_manifest(unknown, entries)

    duplicate = json.loads(json.dumps(manifest))
    duplicate["pins"].append(dict(duplicate["pins"][0]))
    with pytest.raises(RevisionPinError, match="duplicate"):
        validate_manifest(duplicate, entries)


def test_template_covers_exactly_all_unpinned_models():
    entries = build_catalog()
    template = template_manifest(entries)
    expected = sorted(item.model_id for item in entries if item.revision_status == "UNPINNED")
    actual = sorted(row["model_id"] for row in template["pins"])
    assert actual == expected
    assert len(actual) == 21


def test_complete_manifest_rejects_partial():
    entries, _, manifest = _one_pin()
    with pytest.raises(RevisionPinError, match="complete manifest mismatch"):
        validate_manifest(manifest, entries, require_complete=True)


def test_revision_report_counts_after_application():
    entries, _, manifest = _one_pin()
    before = revision_report(entries)
    after = revision_report(apply_manifest(entries, manifest))
    assert after["pinned"] == before["pinned"] + 1
    assert after["unpinned"] == before["unpinned"] - 1
