from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from loto.provider_sandbox import (
    MountKind,
    MountMode,
    ResourceLimits,
    SandboxBackend,
    SandboxExecutionRequest,
    SandboxMount,
    SandboxPolicy,
)


def limits() -> ResourceLimits:
    return ResourceLimits(
        pids=1,
        cpu_cores=1.0,
        memory_bytes=1,
        file_size_bytes=1,
        output_bytes=1,
        wall_timeout_seconds=1.0,
    )


def test_unknown_fields_and_strict_types_are_rejected(policy: SandboxPolicy) -> None:
    data = policy.model_dump(mode="python")
    data["unknown"] = True
    with pytest.raises(ValidationError):
        SandboxPolicy.model_validate(data)
    bad_limits = limits().model_dump(mode="python")
    bad_limits["pids"] = "1"
    with pytest.raises(ValidationError):
        ResourceLimits.model_validate(bad_limits)


def test_none_backend_rejected_for_untrusted_code() -> None:
    with pytest.raises(ValidationError, match="NONE"):
        SandboxPolicy.create(
            policy_id="none",
            backend=SandboxBackend.NONE,
            untrusted_remote_code=True,
            mounts=(),
            environment_allowlist=(),
            environment_deny_patterns=(),
            executable_allowlist=("/usr/bin/python3",),
            limits=limits(),
        )


def test_read_write_model_mount_rejected() -> None:
    with pytest.raises(ValidationError, match="READ_ONLY"):
        SandboxMount(
            mount_id="model",
            kind=MountKind.MODEL_SNAPSHOT,
            mode=MountMode.READ_WRITE_TMP,
            source_path="/model",
            target_path="/sandbox/model",
        )


def test_missing_limits_rejected(policy: SandboxPolicy) -> None:
    data = policy.model_dump(mode="python")
    data.pop("limits")
    with pytest.raises(ValidationError):
        SandboxPolicy.model_validate(data)


def test_rootless_oci_requires_pinned_image() -> None:
    with pytest.raises(ValidationError, match="digest-pinned"):
        SandboxPolicy.create(
            policy_id="oci",
            backend=SandboxBackend.ROOTLESS_OCI,
            untrusted_remote_code=True,
            mounts=(),
            environment_allowlist=(),
            environment_deny_patterns=(),
            executable_allowlist=("/usr/bin/python3",),
            limits=limits(),
            oci_image="example/provider:latest",
        )


def test_request_rejects_partial_control_separator() -> None:
    with pytest.raises(ValidationError):
        SandboxExecutionRequest(
            request_id="request",
            run_id="run",
            executable="/usr/bin/python3",
            arguments=(),
            environment={"SAFE": "line1\nline2"},
            issued_at=datetime.now(timezone.utc),
        )
