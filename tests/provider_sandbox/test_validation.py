from __future__ import annotations

from pathlib import Path

import pytest

from loto.provider_sandbox import SandboxExecutionRequest, validate_policy_paths, validate_request


class Inspector:
    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def is_symlink(self, path: str) -> bool:
        return Path(path).is_symlink()

    def is_directory(self, path: str) -> bool:
        return Path(path).is_dir()


def test_network_and_root_defaults_are_deny_and_read_only(policy) -> None:
    assert policy.network_mode.value == "DISABLED"
    assert policy.root_filesystem.value == "READ_ONLY"
    assert policy.no_new_privileges is True
    assert policy.drop_all_capabilities is True


def test_secret_environment_is_rejected(policy, execution_request) -> None:
    data = execution_request.model_dump(mode="python")
    data["environment"] = {"AWS_SECRET_ACCESS_KEY": "not-retained"}
    altered = SandboxExecutionRequest.model_validate(data)
    with pytest.raises(ValueError, match="not allowlisted|secret-bearing"):
        validate_request(policy, altered)


def test_custom_secret_pattern_is_rejected(policy, execution_request) -> None:
    data = execution_request.model_dump(mode="python")
    data["environment"] = {"CUSTOM_SECRET_VALUE": "x"}
    altered = SandboxExecutionRequest.model_validate(data)
    with pytest.raises(ValueError):
        validate_request(policy, altered)


def test_unauthorized_gpu_rejected(policy, execution_request) -> None:
    data = execution_request.model_dump(mode="python")
    data["requested_gpu_devices"] = ("GPU-OTHER",)
    altered = SandboxExecutionRequest.model_validate(data)
    with pytest.raises(ValueError, match="GPU"):
        validate_request(policy, altered)


def test_path_traversal_rejected(policy) -> None:
    values = policy.model_dump(mode="python", exclude={"policy_sha256"})
    for mount in values["mounts"]:
        if mount["mount_id"] == "repo":
            mount["source_path"] = "/tmp/../etc"
            break
    traversing = type(policy).create(**values)
    with pytest.raises(ValueError, match="traversal"):
        validate_policy_paths(traversing, Inspector())


def test_symlink_source_rejected(policy, sandbox_paths) -> None:
    link = sandbox_paths["repo"].parent / "repo-link"
    link.symlink_to(sandbox_paths["repo"], target_is_directory=True)
    values = policy.model_dump(mode="python", exclude={"policy_sha256"})
    for mount in values["mounts"]:
        if mount["mount_id"] == "repo":
            mount["source_path"] = str(link)
            break
    linked = type(policy).create(**values)
    with pytest.raises(ValueError, match="symlink"):
        validate_policy_paths(linked, Inspector())


def test_valid_paths_pass(policy) -> None:
    validate_policy_paths(policy, Inspector())


def test_parent_symlink_component_rejected(policy, sandbox_paths) -> None:
    parent = sandbox_paths["repo"].parent
    linked_parent = parent.parent / "linked-parent"
    linked_parent.symlink_to(parent, target_is_directory=True)
    values = policy.model_dump(mode="python", exclude={"policy_sha256"})
    for mount in values["mounts"]:
        if mount["mount_id"] == "repo":
            mount["source_path"] = str(linked_parent / "repo")
            break
    linked = type(policy).create(**values)
    with pytest.raises(ValueError, match="symlink"):
        validate_policy_paths(linked, Inspector())
