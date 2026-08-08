from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.research_sources.models import ResearchSourceRegistry
from loto.research_sources.registry import DuplicateJsonKeyError, load_registry

REGISTRY = Path("configs/research_sources/registry.v1.json")


def payload() -> dict[str, object]:
    return load_registry(REGISTRY).model_dump(mode="json")


def validate(data: dict[str, object]) -> ResearchSourceRegistry:
    return ResearchSourceRegistry.model_validate_json(json.dumps(data))


def first_record(data: dict[str, object]) -> dict[str, object]:
    records = data["records"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    return record


def promote_first_model_to_verified(data: dict[str, object]) -> dict[str, object]:
    record = first_record(data)
    record["release_status"] = "AVAILABLE"
    record["source_revision"] = "a" * 40
    record["model_revision"] = "b" * 40
    for artifact in record["required_files"]:
        artifact["size_bytes"] = 1
        artifact["sha256"] = "c" * 64
    compatibility = record["runtime_compatibility"]
    compatibility["python"] = ">=3.11,<3.14"
    compatibility["torch"] = "2.9.1"
    compatibility["transformers"] = "4.57.6"
    compatibility["verification_status"] = "VERIFIED"
    compatibility["packages"][0]["version"] = "1.0.0"
    record["verification"]["status"] = "VERIFIED_FOR_INTAKE"
    record["verification"]["blockers"] = []
    return record


def test_repository_object_requires_concrete_https_url() -> None:
    data = payload()
    first_record(data)["official_source_repository"]["url"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="URL must use https"):
        validate(data)


def test_repository_url_rejects_internal_whitespace() -> None:
    data = payload()
    first_record(data)["official_source_repository"]["url"] = "https://github.com/example/repo name"
    with pytest.raises(ValidationError, match="whitespace"):
        validate(data)


def test_mirror_flag_requires_mirror_repository_type() -> None:
    data = payload()
    repository = first_record(data)["official_source_repository"]
    repository["canonical"] = False
    repository["mirror"] = True
    repository["repository_type"] = "source"
    with pytest.raises(ValidationError, match="mirror=true"):
        validate(data)


def test_floating_package_version_rejected() -> None:
    data = payload()
    first_record(data)["runtime_compatibility"]["packages"][0]["version"] = "latest"
    with pytest.raises(ValidationError, match="floating label"):
        validate(data)


def test_verified_intake_requires_concrete_paper_identity() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["official_paper_url"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="concrete paper identity"):
        validate(data)


def test_verified_intake_requires_canonical_official_repository() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["official_source_repository"]["canonical"] = False
    with pytest.raises(ValidationError, match="canonical and official"):
        validate(data)


def test_verified_intake_requires_available_release() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["release_status"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="release_status=AVAILABLE"):
        validate(data)


def test_verified_intake_requires_required_artifact_sizes() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["required_files"][0]["size_bytes"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="required artifact sizes"):
        validate(data)


def test_verified_intake_requires_required_artifact_hashes() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["required_files"][0]["sha256"] = "UNVERIFIED"
    with pytest.raises(ValidationError, match="required artifact SHA-256"):
        validate(data)


def test_verified_intake_requires_resolved_license_evidence() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["license_boundary"]["code_license_source"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="code license source"):
        validate(data)


def test_verified_intake_cannot_retain_blockers() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["verification"]["blockers"] = ["still unresolved"]
    with pytest.raises(ValidationError, match="cannot retain unresolved blockers"):
        validate(data)


def test_remote_code_allowed_files_are_safe_and_unique() -> None:
    data = payload()
    record = first_record(data)
    record["remote_code_policy"] = {
        "trust_remote_code": True,
        "review_status": "REMOTE_CODE_REVIEW_REQUIRED",
        "policy_id": "remote-review-v1",
        "allowed_files": ["modeling.py", "modeling.py"],
    }
    with pytest.raises(ValidationError, match="duplicate remote-code"):
        validate(data)

    data = payload()
    record = first_record(data)
    record["remote_code_policy"] = {
        "trust_remote_code": True,
        "review_status": "REMOTE_CODE_REVIEW_REQUIRED",
        "policy_id": "remote-review-v1",
        "allowed_files": [".." + "/modeling.py"],
    }
    with pytest.raises(ValidationError, match="artifact path"):
        validate(data)


def test_verified_remote_code_requires_allowed_inventory() -> None:
    data = payload()
    record = first_record(data)
    record["remote_code_policy"] = {
        "trust_remote_code": True,
        "review_status": "VERIFIED",
        "policy_id": "remote-review-v1",
        "allowed_files": [],
    }
    with pytest.raises(ValidationError, match="non-empty allowed file inventory"):
        validate(data)


def test_reviewed_remote_file_must_be_pinned_in_artifact_inventory() -> None:
    data = payload()
    record = first_record(data)
    record["remote_code_policy"] = {
        "trust_remote_code": True,
        "review_status": "VERIFIED",
        "policy_id": "remote-review-v1",
        "allowed_files": ["missing.py"],
    }
    with pytest.raises(ValidationError, match="must exist in artifact inventory"):
        validate(data)


def test_reviewed_remote_code_can_reach_verified_intake() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["remote_code_policy"] = {
        "trust_remote_code": True,
        "review_status": "VERIFIED",
        "policy_id": "remote-review-v1",
        "allowed_files": ["README.md"],
    }
    registry = validate(data)
    assert registry.records[0].verification.status.value == "VERIFIED_FOR_INTAKE"
