from __future__ import annotations

from datetime import datetime, timezone

from loto.provider_sandbox import (
    BackendEvidence,
    SandboxBackend,
    SandboxExecutionRequest,
    SandboxPolicy,
    build_argv_plan,
)

ZERO = "0" * 64


def test_bubblewrap_plan_is_argv_and_keeps_injection_literal(
    policy, execution_request, backend
) -> None:
    data = execution_request.model_dump(mode="python")
    injection = "; touch /tmp/should-not-exist"
    data["arguments"] = ("provider.py", injection)
    altered = SandboxExecutionRequest.model_validate(data)
    plan = build_argv_plan(policy, altered, backend)
    assert plan.argv[0] == "/usr/bin/bwrap"
    assert "--unshare-net" in plan.argv
    assert "--cap-drop" in plan.argv
    assert injection in plan.argv
    assert " ".join(plan.argv) not in plan.argv


def test_rootless_oci_plan_has_required_controls(policy, execution_request) -> None:
    values = policy.model_dump(mode="python", exclude={"policy_sha256"})
    values["backend"] = SandboxBackend.ROOTLESS_OCI
    values["oci_image"] = "registry.example/provider@sha256:" + "1" * 64
    oci_policy = SandboxPolicy.create(**values)
    backend = BackendEvidence(
        backend=SandboxBackend.ROOTLESS_OCI,
        available=True,
        executable_path="/usr/bin/podman",
        executable_sha256=ZERO,
        version="podman fixture",
        rootless=True,
        detected_at=datetime.now(timezone.utc),
    )
    request_values = execution_request.model_dump(mode="python")
    request_values["requested_gpu_devices"] = ("GPU-TEST",)
    gpu_request = SandboxExecutionRequest.model_validate(request_values)
    plan = build_argv_plan(oci_policy, gpu_request, backend)
    assert "--network=none" in plan.argv
    assert "--read-only" in plan.argv
    assert "--cap-drop=ALL" in plan.argv
    assert "--security-opt=no-new-privileges" in plan.argv
    assert oci_policy.oci_image in plan.argv


def test_bubblewrap_gpu_request_fails_closed(
    policy, execution_request, backend
) -> None:
    import pytest

    values = execution_request.model_dump(mode="python")
    values["requested_gpu_devices"] = ("GPU-TEST",)
    gpu_request = SandboxExecutionRequest.model_validate(values)
    with pytest.raises(ValueError, match="GPU isolation"):
        build_argv_plan(policy, gpu_request, backend)
