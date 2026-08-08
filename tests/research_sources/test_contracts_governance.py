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


def test_package_version_range_rejected() -> None:
    data = payload()
    first_record(data)["runtime_compatibility"]["packages"][0]["version"] = ">=1,<2"
    with pytest.raises(ValidationError, match="one exact version"):
        validate(data)


def test_duplicate_normalized_package_identity_rejected() -> None:
    data = payload()
    compatibility = first_record(data)["runtime_compatibility"]
    duplicate = copy.deepcopy(compatibility["packages"][0])
    duplicate["name"] = duplicate["name"].replace("-", "_")
    compatibility["packages"].append(duplicate)
    with pytest.raises(ValidationError, match="duplicate package identity"):
        validate(data)


def test_verified_intake_requires_concrete_paper_title_and_identifier() -> None:
    for field in ("paper_title", "paper_identifier"):
        data = payload()
        record = promote_first_model_to_verified(data)
        record[field] = "UNKNOWN"
        with pytest.raises(ValidationError, match="concrete paper identity"):
            validate(data)


def test_verified_intake_requires_repository_type_consistency() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["official_source_repository"]["repository_type"] = "model"
    with pytest.raises(ValidationError, match="source repository has an invalid"):
        validate(data)

    data = payload()
    record = promote_first_model_to_verified(data)
    record["official_model_repository"]["repository_type"] = "source"
    with pytest.raises(ValidationError, match="model repository has an invalid"):
        validate(data)


def test_verified_intake_requires_verified_runtime_compatibility() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["runtime_compatibility"]["verification_status"] = "UNVERIFIED"
    with pytest.raises(ValidationError, match="verified runtime compatibility"):
        validate(data)


def test_verified_compatibility_rejects_unresolved_package_identity() -> None:
    data = payload()
    compatibility = first_record(data)["runtime_compatibility"]
    compatibility["verification_status"] = "VERIFIED"
    compatibility["python"] = ">=3.11,<3.14"
    compatibility["torch"] = "2.9.1"
    compatibility["transformers"] = "4.57.6"
    compatibility["packages"][0]["version"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="resolved package identity"):
        validate(data)


def test_verified_intake_requires_resolved_contamination_evidence() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["contamination"]["evidence_status"] = "UNVERIFIED"
    with pytest.raises(ValidationError, match="resolved contamination evidence"):
        validate(data)

    data = payload()
    record = promote_first_model_to_verified(data)
    record["contamination"]["benchmark_contamination_risk"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="resolved risk"):
        validate(data)


def test_verified_intake_requires_complete_official_url_evidence() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    model_url = record["official_model_repository"]["url"]
    record["verification"]["official_urls_checked"].remove(model_url)
    with pytest.raises(ValidationError, match="missing official URL"):
        validate(data)


def test_reviewed_remote_file_must_be_required() -> None:
    data = payload()
    record = promote_first_model_to_verified(data)
    record["required_files"][0]["required"] = False
    record["remote_code_policy"] = {
        "trust_remote_code": True,
        "review_status": "VERIFIED",
        "policy_id": "remote-review-v1",
        "allowed_files": [record["required_files"][0]["path"]],
    }
    with pytest.raises(ValidationError, match="must be a required artifact"):
        validate(data)


def test_non_remote_policy_rejects_allowed_files() -> None:
    data = payload()
    record = first_record(data)
    record["remote_code_policy"]["allowed_files"] = ["modeling.py"]
    with pytest.raises(ValidationError, match="requires an empty allowed file"):
        validate(data)


def test_remote_code_status_requires_pending_review_policy() -> None:
    data = payload()
    record = first_record(data)
    record["verification"]["status"] = "REMOTE_CODE_REVIEW_REQUIRED"
    with pytest.raises(ValidationError, match="requires a pending remote-code review"):
        validate(data)


def test_not_released_status_requires_not_released_release_state() -> None:
    data = payload()
    record = first_record(data)
    record["verification"]["status"] = "NOT_RELEASED"
    record["release_status"] = "AVAILABLE"
    with pytest.raises(ValidationError, match="requires release_status=NOT_RELEASED"):
        validate(data)
