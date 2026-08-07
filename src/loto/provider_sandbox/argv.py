"""Deterministic argv-only builders for supported sandbox backends."""

from __future__ import annotations

from pathlib import PurePosixPath

from .contracts import (
    BackendEvidence,
    MountKind,
    MountMode,
    SandboxArgvPlan,
    SandboxBackend,
    SandboxExecutionRequest,
    SandboxPolicy,
)
from .validation import validate_request


def _mount_arguments(policy: SandboxPolicy) -> list[str]:
    argv: list[str] = []
    for mount in sorted(policy.mounts, key=lambda item: item.mount_id):
        if mount.kind == MountKind.TMPFS:
            argv.extend(("--tmpfs", mount.target_path))
        elif mount.mode == MountMode.READ_ONLY:
            assert mount.source_path is not None
            argv.extend(("--ro-bind", mount.source_path, mount.target_path))
        else:
            assert mount.source_path is not None
            argv.extend(("--bind", mount.source_path, mount.target_path))
    return argv


def _bwrap_plan(
    policy: SandboxPolicy,
    request: SandboxExecutionRequest,
    backend: BackendEvidence,
) -> tuple[str, ...]:
    assert backend.executable_path is not None
    argv = [
        backend.executable_path,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--unshare-net",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
    ]
    argv.extend(_mount_arguments(policy))
    for key in sorted(request.environment):
        argv.extend(("--setenv", key, request.environment[key]))
    argv.append("--")
    argv.append(request.executable)
    argv.extend(request.arguments)
    return tuple(argv)


def _oci_mount(mount: object) -> str:
    source_path = getattr(mount, "source_path")
    target_path = getattr(mount, "target_path")
    mode = getattr(mount, "mode")
    if getattr(mount, "kind") == MountKind.TMPFS:
        return f"type=tmpfs,destination={target_path},rw,noexec,nosuid,nodev"
    suffix = "ro" if mode == MountMode.READ_ONLY else "rw"
    return f"type=bind,source={source_path},destination={target_path},{suffix},nosuid,nodev"


def _oci_plan(
    policy: SandboxPolicy,
    request: SandboxExecutionRequest,
    backend: BackendEvidence,
) -> tuple[str, ...]:
    assert backend.executable_path is not None
    assert policy.oci_image is not None
    argv = [
        backend.executable_path,
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--userns=keep-id",
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
        f"--pids-limit={policy.limits.pids}",
        f"--memory={policy.limits.memory_bytes}",
        f"--cpus={policy.limits.cpu_cores}",
        f"--ulimit=fsize={policy.limits.file_size_bytes}:{policy.limits.file_size_bytes}",
    ]
    for mount in sorted(policy.mounts, key=lambda item: item.mount_id):
        argv.extend(("--mount", _oci_mount(mount)))
    for key in sorted(request.environment):
        argv.extend(("--env", f"{key}={request.environment[key]}"))
    for device in request.requested_gpu_devices:
        argv.extend(("--device", f"nvidia.com/gpu={device}"))
    argv.append(policy.oci_image)
    argv.append(request.executable)
    argv.extend(request.arguments)
    return tuple(argv)


def build_argv_plan(
    policy: SandboxPolicy,
    request: SandboxExecutionRequest,
    backend: BackendEvidence,
) -> SandboxArgvPlan:
    validate_request(policy, request)
    if not backend.available:
        raise ValueError("requested sandbox backend is unavailable")
    if backend.backend != policy.backend:
        raise ValueError("backend evidence does not match policy")
    if backend.backend == SandboxBackend.NONE:
        if policy.untrusted_remote_code:
            raise ValueError("NONE backend forbidden for untrusted remote code")
        argv = (request.executable, *request.arguments)
    elif backend.backend == SandboxBackend.BUBBLEWRAP:
        if request.requested_gpu_devices:
            raise ValueError(
                "BUBBLEWRAP GPU isolation is not proven by environment filtering"
            )
        argv = _bwrap_plan(policy, request, backend)
    elif backend.backend == SandboxBackend.ROOTLESS_OCI:
        argv = _oci_plan(policy, request, backend)
    else:
        raise ValueError("unsupported sandbox backend")
    if any("\x00" in item for item in argv):
        raise ValueError("argv cannot contain NUL")
    if not PurePosixPath(argv[0]).is_absolute():
        raise ValueError("backend executable path must be absolute")
    return SandboxArgvPlan.create(
        backend=backend.backend,
        argv=argv,
        environment_keys=tuple(sorted(request.environment)),
    )
