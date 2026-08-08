"""Pure fail-closed policy and effective-evidence validation."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Protocol

from .canonical import sha256_bytes, sha256_canonical
from .contracts import (
    EffectiveSandboxEvidence,
    MountKind,
    MountMode,
    SandboxExecutionRequest,
    SandboxPolicy,
    SandboxVerificationReport,
    VerificationStatus,
)

DEFAULT_SECRET_PATTERNS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
    "AUTHORIZATION",
    "COOKIE",
    "DSN",
    "DATABASE_URL",
    "MLFLOW_TRACKING_URI",
    "AWS_",
    "GCP_",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_",
    "SSH_",
    "DOCKER_",
)
PROHIBITED_TARGETS = (
    "/var/run/docker.sock",
    "/run/docker.sock",
    "/run/podman/podman.sock",
    "/root",
    "/home",
)
PROHIBITED_SOURCE_PARTS = (
    ".ssh",
    ".aws",
    ".azure",
    ".config/gcloud",
    "docker.sock",
    "podman.sock",
)
SHELL_EXECUTABLES = frozenset({"sh", "bash", "zsh", "fish", "dash", "cmd.exe", "powershell"})


class PathInspector(Protocol):
    def exists(self, path: str) -> bool: ...

    def is_symlink(self, path: str) -> bool: ...

    def is_directory(self, path: str) -> bool: ...


def _normalized_absolute(path: str) -> str:
    parsed = PurePosixPath(path)
    if not parsed.is_absolute():
        raise ValueError("path must be absolute")
    if ".." in parsed.parts or "." in parsed.parts:
        raise ValueError("path traversal and dot components are forbidden")
    normalized = str(parsed)
    if normalized != path or "//" in path:
        raise ValueError("path must be canonical")
    return normalized


def validate_policy_paths(policy: SandboxPolicy, inspector: PathInspector) -> None:
    targets: list[str] = []
    for mount in policy.mounts:
        target = _normalized_absolute(mount.target_path)
        if any(target == item or target.startswith(f"{item}/") for item in PROHIBITED_TARGETS):
            raise ValueError(f"prohibited mount target: {target}")
        targets.append(target)
        if mount.kind == MountKind.TMPFS:
            continue
        assert mount.source_path is not None
        source = _normalized_absolute(mount.source_path)
        lowered = source.lower()
        if any(part.lower() in lowered for part in PROHIBITED_SOURCE_PARTS):
            raise ValueError(f"prohibited mount source: {source}")
        if not inspector.exists(source):
            raise ValueError(f"mount source does not exist: {source}")
        current = PurePosixPath("/")
        for component in PurePosixPath(source).parts[1:]:
            current = current / component
            if inspector.is_symlink(str(current)):
                raise ValueError(f"symlink mount source component forbidden: {current}")
        if mount.kind in {MountKind.REPOSITORY, MountKind.MODEL_SNAPSHOT, MountKind.OUTPUT}:
            if not inspector.is_directory(source):
                raise ValueError(f"mount source must be a directory: {source}")
    for left_index, left in enumerate(targets):
        for right in targets[left_index + 1 :]:
            if left.startswith(f"{right}/") or right.startswith(f"{left}/"):
                raise ValueError("nested mount targets are forbidden")


def validate_request(policy: SandboxPolicy, request: SandboxExecutionRequest) -> None:
    if request.executable not in policy.executable_allowlist:
        raise ValueError("requested executable is not allowlisted")
    executable_name = PurePosixPath(request.executable).name.lower()
    if executable_name in SHELL_EXECUTABLES:
        raise ValueError("shell executables are forbidden")
    unknown_env = sorted(set(request.environment) - set(policy.environment_allowlist))
    if unknown_env:
        raise ValueError(f"environment keys are not allowlisted: {unknown_env}")
    deny_patterns = tuple(DEFAULT_SECRET_PATTERNS) + policy.environment_deny_patterns
    for key in request.environment:
        if any(re.search(pattern, key, flags=re.IGNORECASE) for pattern in deny_patterns):
            raise ValueError(f"secret-bearing environment key forbidden: {key}")
    unauthorized_gpu = sorted(set(request.requested_gpu_devices) - set(policy.gpu_device_allowlist))
    if unauthorized_gpu:
        raise ValueError(f"GPU devices are not allowlisted: {unauthorized_gpu}")


def verify_effective_evidence(
    policy: SandboxPolicy,
    request: SandboxExecutionRequest,
    effective: EffectiveSandboxEvidence,
) -> SandboxVerificationReport:
    missing: list[str] = []
    mismatches: list[str] = []

    def compare(name: str, actual: object, expected: object) -> None:
        if actual is None:
            missing.append(name)
        elif actual != expected:
            mismatches.append(name)

    compare("backend", effective.backend, policy.backend)
    compare("network-disabled", effective.network_disabled, True)
    compare("root-read-only", effective.root_read_only, True)
    compare("no-new-privileges", effective.no_new_privileges, True)
    compare("capabilities-dropped", effective.all_capabilities_dropped, True)
    compare("resource-limits", effective.limits, policy.limits)

    if effective.mounts is None:
        missing.append("mounts")
    else:
        requested_mounts = {
            item.mount_id: (
                item.kind,
                item.mode,
                item.target_path,
                sha256_bytes(item.source_path.encode("utf-8"))
                if item.source_path is not None
                else None,
            )
            for item in policy.mounts
        }
        observed_mounts = {
            item.mount_id: (
                item.kind,
                item.mode,
                item.target_path,
                item.source_path_sha256,
            )
            for item in effective.mounts
        }
        if requested_mounts != observed_mounts:
            mismatches.append("mounts")
        if any(
            item.mode == MountMode.READ_WRITE_TMP
            and item.kind not in {MountKind.OUTPUT, MountKind.TMPFS}
            for item in effective.mounts
        ):
            mismatches.append("writable-mount-boundary")

    if effective.environment_keys is None:
        missing.append("environment")
    elif tuple(sorted(effective.environment_keys)) != tuple(sorted(request.environment)):
        mismatches.append("environment")

    if effective.gpu_devices is None:
        missing.append("gpu-devices")
    elif tuple(effective.gpu_devices) != tuple(request.requested_gpu_devices):
        mismatches.append("gpu-devices")

    if mismatches:
        status = VerificationStatus.MISMATCH
    elif missing:
        status = VerificationStatus.INCOMPLETE
    else:
        status = VerificationStatus.VERIFIED
    payload = {
        "schema_version": "1.0.0",
        "status": status,
        "verified": status == VerificationStatus.VERIFIED,
        "policy_sha256": policy.policy_sha256,
        "effective_evidence_sha256": effective.evidence_sha256,
        "missing_checks": tuple(sorted(set(missing))),
        "mismatches": tuple(sorted(set(mismatches))),
    }
    return SandboxVerificationReport(
        report_sha256=sha256_canonical(payload),
        **payload,
    )
