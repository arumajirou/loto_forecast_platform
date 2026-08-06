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
    record["verification"]["status"] = "VERIFIED_FOR_INTAKE"
    record["verification"]["blockers"] = []
    return record


def test_initial_registry_is_valid() -> None:
    registry = load_registry(REGISTRY)
    assert len(registry.records) == 11


def test_duplicate_source_id_rejected() -> None:
    data = payload()
    records = data["records"]
    assert isinstance(records, list)
    records[1]["source_id"] = records[0]["source_id"]
    with pytest.raises(ValidationError, match="duplicate source_id"):
        validate(data)


def test_duplicate_logical_model_id_rejected() -> None:
    data = payload()
    records = data["records"]
    assert isinstance(records, list)
    records[1]["logical_model_id"] = records[0]["logical_model_id"]
    with pytest.raises(ValidationError, match="duplicate logical model_id"):
        validate(data)


def test_malformed_revision_rejected() -> None:
    data = payload()
    first_record(data)["source_revision"] = "main"
    with pytest.raises(ValidationError, match="revision must be"):
        validate(data)


def test_uppercase_revision_rejected() -> None:
    data = payload()
    first_record(data)["source_revision"] = "A" * 40
    with pytest.raises(ValidationError, match="revision must be"):
        validate(data)


def test_unpinned_formal_source_rejected() -> None:
    data = payload()
    record = first_record(data)
    record["source_revision"] = "UNPINNED"
    record["model_revision"] = "a" * 40
    record["verification"]["status"] = "VERIFIED_FOR_INTAKE"
    with pytest.raises(ValidationError, match="verified formal source"):
        validate(data)


def test_unpinned_formal_model_rejected() -> None:
    data = payload()
    record = first_record(data)
    record["model_revision"] = "UNPINNED"
    record["verification"]["status"] = "VERIFIED_FOR_INTAKE"
    with pytest.raises(ValidationError, match="verified model intake"):
        validate(data)


def test_uppercase_sha256_rejected() -> None:
    data = payload()
    first_record(data)["required_files"][0]["sha256"] = "A" * 64
    with pytest.raises(ValidationError, match="sha256 must be lowercase"):
        validate(data)


def test_malformed_sha256_rejected() -> None:
    data = payload()
    first_record(data)["required_files"][0]["sha256"] = "abc"
    with pytest.raises(ValidationError, match="sha256 must be lowercase"):
        validate(data)


def test_unsafe_relative_path_rejected() -> None:
    unsafe_paths = (
        ".." + "/weight.bin",
        chr(47) + "weight.bin",
        "a" + chr(92) + "b",
        "." + "/weight.bin",
    )
    for path in unsafe_paths:
        data = payload()
        first_record(data)["required_files"][0]["path"] = path
        with pytest.raises(ValidationError, match="artifact path"):
            validate(data)


def test_duplicate_artifact_path_rejected() -> None:
    data = payload()
    record = first_record(data)
    duplicate = copy.deepcopy(record["required_files"][0])
    record["required_files"].append(duplicate)
    with pytest.raises(ValidationError, match="duplicate artifact path"):
        validate(data)


def test_code_and_weight_license_must_be_separate_fields() -> None:
    data = payload()
    del first_record(data)["license_boundary"]["weight_license"]
    with pytest.raises(ValidationError, match="weight_license"):
        validate(data)


def test_remote_code_requires_review_policy() -> None:
    data = payload()
    record = first_record(data)
    record["remote_code_policy"] = {
        "trust_remote_code": True,
        "review_status": "UNVERIFIED",
        "policy_id": "UNKNOWN",
        "allowed_files": [],
    }
    with pytest.raises(ValidationError, match="remote code requires"):
        validate(data)


def test_not_released_cannot_be_available_for_intake() -> None:
    data = payload()
    record = first_record(data)
    record["release_status"] = "NOT_RELEASED"
    record["verification"]["status"] = "CHECKPOINT_REVIEW_REQUIRED"
    with pytest.raises(ValidationError, match="not-released source"):
        validate(data)


def test_nonofficial_mirror_cannot_be_canonical() -> None:
    data = payload()
    record = first_record(data)
    record["official_source_repository"] = {
        "url": "https://github.com/example/mirror",
        "repository_type": "mirror",
        "official": False,
        "canonical": True,
        "mirror": True,
    }
    with pytest.raises(ValidationError, match="canonical repository"):
        validate(data)


def test_superseded_revision_cycle_rejected() -> None:
    data = payload()
    records = data["records"]
    records[0]["superseded_by_source_id"] = records[1]["source_id"]
    records[1]["superseded_by_source_id"] = records[0]["source_id"]
    with pytest.raises(ValidationError, match="cycle"):
        validate(data)


def test_unknown_field_rejected() -> None:
    data = payload()
    first_record(data)["runtime_certified"] = False
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate(data)


def test_bool_int_coercion_rejected() -> None:
    data = payload()
    first_record(data)["required_files"][0]["required"] = 1
    with pytest.raises(ValidationError, match="valid boolean"):
        validate(data)


def test_naive_datetime_rejected() -> None:
    data = payload()
    data["generated_at"] = "2026-08-06T06:52:00"
    with pytest.raises(ValidationError, match="timezone"):
        validate(data)


def test_duplicate_json_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text('{"schema_version":"1.0.0","schema_version":"1.0.0"}', encoding="utf-8")
    with pytest.raises(DuplicateJsonKeyError):
        load_registry(path)


def test_repository_object_requires_concrete_https_url() -> None:
    data = payload()
    first_record(data)["official_source_repository"]["url"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="URL must use https"):
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
